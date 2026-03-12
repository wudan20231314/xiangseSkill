export const config = {
  httpTimeoutMs: Number(process.env.VALIDATOR_HTTP_TIMEOUT_MS || 15000),
  jsTimeoutMs: Number(process.env.VALIDATOR_JS_TIMEOUT_MS || 1200),
  webViewTimeoutMs: Number(process.env.VALIDATOR_WEBVIEW_TIMEOUT_MS || 25000),
  webViewHeadless: String(process.env.VALIDATOR_WEBVIEW_HEADLESS || "true").toLowerCase() !== "false"
};
