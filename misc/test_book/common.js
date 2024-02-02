function getHttpResult(http) {
  try {
    return `${http.status}<br>` + JSON.stringify(JSON.parse(http.responseText), null, 4);
  } catch (error) {
    return `${http.status} ${http.responseURL}<br>` + http.responseText.replace(/</gi, "&lt;").replace(/>/gi, "&gt;");
  }
}
