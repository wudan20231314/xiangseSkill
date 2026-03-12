import { applyTemplate, isJsRule, unwrapJsRule } from "./template.js";
import { runUserJs } from "./jsSandbox.js";
import { resolveWithHost } from "../utils/url.js";

function truthy(value) {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") {
    const v = value.trim().toLowerCase();
    return ["1", "true", "yes", "on"].includes(v);
  }
  return false;
}

function normalizeArray(value) {
  if (Array.isArray(value)) return value.map((x) => String(x || "").trim()).filter(Boolean);
  if (typeof value === "string") {
    return value
      .split(/\r?\n|,/g)
      .map((x) => x.trim())
      .filter(Boolean);
  }
  return [];
}

function extractWebViewOptions(obj) {
  if (!obj || typeof obj !== "object") return {};
  const out = {};
  if (Object.prototype.hasOwnProperty.call(obj, "webView")) out.webView = truthy(obj.webView);
  if (Object.prototype.hasOwnProperty.call(obj, "webViewJs")) out.webViewJs = String(obj.webViewJs || "");
  if (Object.prototype.hasOwnProperty.call(obj, "webViewJsDelay")) out.webViewJsDelay = Number(obj.webViewJsDelay || 0);
  if (Object.prototype.hasOwnProperty.call(obj, "webViewSkipUrls")) out.webViewSkipUrls = normalizeArray(obj.webViewSkipUrls);
  if (Object.prototype.hasOwnProperty.call(obj, "webViewSkipUrlsUnless")) out.webViewSkipUrlsUnless = normalizeArray(obj.webViewSkipUrlsUnless);
  if (Object.prototype.hasOwnProperty.call(obj, "webViewContentRules")) out.webViewContentRules = obj.webViewContentRules;
  if (Object.prototype.hasOwnProperty.call(obj, "webViewSniff")) out.webViewSniff = obj.webViewSniff;
  return out;
}

function mergeWebViewOptions(...parts) {
  return parts.reduce((acc, part) => ({ ...acc, ...(part || {}) }), {});
}

export async function buildRequest(input) {
  const { sourceConfig, actionConfig, params, result } = input;
  const host = String(actionConfig?.host || sourceConfig?.sourceUrl || "");
  const baseHeaders = {
    ...(sourceConfig?.httpHeaders || {}),
    ...(actionConfig?.httpHeaders || {})
  };
  const actionWebViewOptions = extractWebViewOptions(actionConfig);

  const requestInfo = actionConfig?.requestInfo;
  if (!requestInfo) {
    throw new Error("requestInfo is required");
  }

  const runtimeConfig = {
    ...sourceConfig,
    ...actionConfig,
    host,
    httpHeaders: baseHeaders
  };

  if (typeof requestInfo === "string") {
    if (isJsRule(requestInfo)) {
      const jsResult = await runUserJs(unwrapJsRule(requestInfo), {
        config: runtimeConfig,
        params,
        result
      });

      if (typeof jsResult === "string") {
        return {
          url: resolveWithHost(host, jsResult),
          method: "GET",
          httpHeaders: baseHeaders,
          ...actionWebViewOptions
        };
      }

      const jsUrl = String(jsResult?.url || "").trim();
      const jsWebViewOptions = extractWebViewOptions(jsResult);
      return {
        url: resolveWithHost(host, jsUrl),
        method: jsResult?.POST ? "POST" : "GET",
        httpParams: jsResult?.httpParams || {},
        httpHeaders: {
          ...baseHeaders,
          ...(jsResult?.httpHeaders || {})
        },
        ...mergeWebViewOptions(actionWebViewOptions, jsWebViewOptions)
      };
    }

    const templated = applyTemplate(requestInfo, {
      keyWord: params?.keyWord,
      pageIndex: params?.pageIndex,
      offset: params?.offset,
      filter: params?.filter,
      result: typeof result === "string" ? result : ""
    });

    return {
      url: resolveWithHost(host, templated),
      method: "GET",
      httpHeaders: baseHeaders,
      ...actionWebViewOptions
    };
  }

  if (typeof requestInfo === "object") {
    const reqWebViewOptions = extractWebViewOptions(requestInfo);
    return {
      url: resolveWithHost(host, String(requestInfo?.url || "")),
      method: requestInfo?.POST ? "POST" : "GET",
      httpParams: requestInfo?.httpParams || {},
      httpHeaders: {
        ...baseHeaders,
        ...(requestInfo?.httpHeaders || {})
      },
      ...mergeWebViewOptions(actionWebViewOptions, reqWebViewOptions)
    };
  }

  throw new Error("Unsupported requestInfo type");
}
