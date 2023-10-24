function boostrap() {
  const organizationUrl = document.getElementById("bootstrap-url").value;
  const sequesterVerifyKey = document.getElementById("sequester-verify-key").value;
  const email = document.getElementById("bootstrap-email").value;
  const key = document.getElementById("bootstrap-key").value;
  const http = new XMLHttpRequest();
  http.open("POST", "http://localhost:5775/organization/bootstrap");
  http.setRequestHeader("Content-type", "application/json");
  http.send(JSON.stringify({
    organization_url: organizationUrl,
    email,
    key,
    sequester_verify_key: sequesterVerifyKey
  }));
  http.onreadystatechange = (e) => {
    document.getElementById("bootstrap-result").innerHTML = getHttpResult(http);
  }
}
