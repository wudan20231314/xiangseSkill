import { parseFieldValue } from "./fieldParser.js";
import { createDom, evaluateNodes } from "./xpath.js";
import { buildRequest } from "./requestBuilder.js";
import { performHttpRequest } from "../services/httpService.js";
import { performWebViewRequest } from "../services/webviewService.js";
import { getFixtureContent } from "../services/fixtureService.js";
import { runUserJs } from "./jsSandbox.js";

const RESERVED_KEYS = new Set([
  "actionID",
  "parserID",
  "responseFormatType",
  "validConfig",
  "requestInfo",
  "host",
  "httpHeaders",
  "list",
  "moreKeys",
  "JSParser",
  "requestJavascript",
  "responseJavascript",
  "requestFunction",
  "responseFunction",
  "webView",
  "webViewJs",
  "webViewJsDelay",
  "webViewSkipUrls",
  "webViewSkipUrlsUnless",
  "webViewContentRules",
  "webViewSniff"
]);

const WEBVIEW_KEYS = [
  "webView",
  "webViewJs",
  "webViewJsDelay",
  "webViewSkipUrls",
  "webViewSkipUrlsUnless",
  "webViewContentRules",
  "webViewSniff"
];

function jsonPathGet(obj, pathExpr) {
  const clean = String(pathExpr || "").trim();
  if (!clean) {
    return obj;
  }

  const normalized = clean.replace(/^\$\.?/, "");
  const segments = normalized.includes("/")
    ? normalized.split("/").filter(Boolean)
    : normalized.split(".").filter(Boolean);

  let current = obj;
  for (const key of segments) {
    if (current == null) {
      return undefined;
    }
    current = current[key];
  }
  return current;
}

async function parseJsonField(expression, item, context) {
  const raw = String(expression || "").trim();
  if (!raw) {
    return "";
  }

  if (raw.startsWith("@js:")) {
    return runUserJs(raw.replace(/^@js:\s*/, ""), { ...context, result: item });
  }

  const pipeIndex = raw.indexOf("||@js:");
  if (pipeIndex >= 0) {
    const basePath = raw.slice(0, pipeIndex).trim();
    const jsCode = raw.slice(pipeIndex + "||@js:".length);
    const base = jsonPathGet(item, basePath);
    return runUserJs(jsCode, { ...context, result: base });
  }

  return jsonPathGet(item, raw);
}

function actionFields(actionConfig) {
  return Object.keys(actionConfig).filter((key) => !RESERVED_KEYS.has(key));
}

function hasNonEmpty(value) {
  if (value == null) return false;
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return Number.isFinite(value) && value !== 0;
  if (typeof value === "string") return value.trim().length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return false;
}

function hasWebViewSignal(action, request) {
  return WEBVIEW_KEYS.some((k) => hasNonEmpty(action?.[k]) || hasNonEmpty(request?.[k]));
}

function resolveRuntimeEngine(input, action, request) {
  const preferred = String(input?.engine || "auto").toLowerCase();
  if (preferred === "http" || preferred === "webview") {
    return preferred;
  }
  return hasWebViewSignal(action, request) ? "webview" : "http";
}

function collectWebViewAppliedKeys(action, request) {
  return WEBVIEW_KEYS.filter((k) => hasNonEmpty(action?.[k]) || hasNonEmpty(request?.[k]));
}

export async function executeStep(input) {
  const startedAt = Date.now();
  const sourceEntry = input.source[input.sourceKey];
  if (!sourceEntry) {
    throw new Error(`sourceKey not found: ${input.sourceKey}`);
  }

  const action = sourceEntry[input.step];
  if (!action) {
    throw new Error(`Missing action: ${input.step}`);
  }

  const issues = [];
  const parseLimit = Math.max(1, Number(input.queryPayload?._parseLimit || 10));
  const request = await buildRequest({
    sourceConfig: sourceEntry,
    actionConfig: action,
    params: input.queryPayload,
    result: input.queryPayload?.result
  });

  let body = "";
  let responseUrl = request.url;
  let fixtureUsed;
  let status = 200;
  let blockedReason = "";
  let webviewTrace = [];
  const runtimeEngine = resolveRuntimeEngine(input, action, request);
  const webviewAppliedKeys = collectWebViewAppliedKeys(action, request);

  if (input.mode === "fixture") {
    const fixture = getFixtureContent(input.step, input.fixturesState);
    if (!fixture) {
      issues.push({
        step: input.step,
        field: "fixture",
        level: "error",
        message: "Fixture mode enabled but no fixture found"
      });
      body = "";
      status = 404;
    } else {
      body = fixture.content;
      fixtureUsed = fixture.used;
      if (runtimeEngine === "webview") {
        webviewTrace.push({
          type: "fixture_replay",
          message: "fixture mode replay, webview runtime skipped"
        });
      }
    }
  } else {
    if (runtimeEngine === "webview") {
      const webviewResult = await performWebViewRequest(request, {
        webViewTimeoutMs: input.webViewTimeoutMs
      });
      body = webviewResult.body;
      responseUrl = webviewResult.responseUrl;
      status = webviewResult.status;
      blockedReason = webviewResult.blockedReason || "";
      webviewTrace = webviewResult.trace || [];
    } else {
      const httpResult = await performHttpRequest(request);
      body = httpResult.body;
      responseUrl = httpResult.responseUrl;
      status = httpResult.status;
      blockedReason = httpResult.blockedReason || "";
    }
    if (status >= 400) {
      issues.push({
        step: input.step,
        field: "http",
        level: "warning",
        message: `HTTP status ${status}`
      });
    }
    if (blockedReason) {
      issues.push({
        step: input.step,
        field: "blocked",
        level: "error",
        message: blockedReason
      });
    }
  }

  const responseType = String(action.responseFormatType || "html").toLowerCase();
  const fields = actionFields(action);

  let listLengthOnlyDebug = 0;
  let list = [];
  let item = {};

  if (responseType === "json") {
    let jsonObj = null;
    try {
      jsonObj = JSON.parse(body || "{}");
    } catch (err) {
      issues.push({
        step: input.step,
        field: "response",
        level: "error",
        message: `Invalid JSON response: ${err?.message || "unknown"}`
      });
      jsonObj = {};
    }

    const listPath = String(action.list || "").trim();
    const ctx = {
      config: { ...sourceEntry, ...action },
      params: {
        ...input.queryPayload,
        responseUrl
      },
      result: null
    };

    if (listPath) {
      const rawList = jsonPathGet(jsonObj, listPath);
      const arr = Array.isArray(rawList) ? rawList : rawList ? [rawList] : [];
      listLengthOnlyDebug = arr.length;

      for (const rawItem of arr.slice(0, parseLimit)) {
        const parsed = {};
        for (const field of fields) {
          parsed[field] = await parseJsonField(String(action[field] || ""), rawItem, {
            ...ctx,
            result: rawItem
          });
        }
        list.push(parsed);
      }
    } else {
      for (const field of fields) {
        item[field] = await parseJsonField(String(action[field] || ""), jsonObj, {
          ...ctx,
          result: jsonObj
        });
      }
    }
  } else {
    const document = createDom(body || "");
    const listExpr = String(action.list || "").trim();

    if (listExpr) {
      const nodes = evaluateNodes(document, listExpr, document);
      listLengthOnlyDebug = nodes.length;
      for (const node of nodes.slice(0, parseLimit)) {
        const parsed = {};
        for (const field of fields) {
          parsed[field] = await parseFieldValue({
            document,
            expression: String(action[field] || ""),
            contextNode: node,
            context: {
              config: { ...sourceEntry, ...action },
              params: {
                ...input.queryPayload,
                responseUrl
              },
              result: null
            }
          });
        }
        list.push(parsed);
      }
    } else {
      for (const field of fields) {
        item[field] = await parseFieldValue({
          document,
          expression: String(action[field] || ""),
          contextNode: document,
          context: {
            config: { ...sourceEntry, ...action },
            params: {
              ...input.queryPayload,
              responseUrl
            },
            result: null
          }
        });
      }
    }
  }

  const elapsedMs = Date.now() - startedAt;
  return {
    step: input.step,
    success: true,
    blocked: Boolean(blockedReason),
    blockedReason,
    requestDebug: {
      request,
      responseUrl,
      mode: input.mode,
      runtimeEngine,
      fixtureUsed,
      status,
      blocked: Boolean(blockedReason),
      blockedReason,
      webviewTrace,
      webviewAppliedKeys
    },
    parseResult: {
      listLengthOnlyDebug,
      list,
      item
    },
    fieldDiagnostics: issues,
    elapsedMs
  };
}
