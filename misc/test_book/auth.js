// LOGIN

function login() {
  const email = document.getElementById("auth-email").value;
  const key = document.getElementById("auth-key").value;
  const organization = document.getElementById("auth-organization-id").value;
  const encryptedKey = document.getElementById("auth-encrypted-key").value;
  const http = new XMLHttpRequest();
  http.open("POST", "http://localhost:5775/auth");
  http.setRequestHeader("Content-type", "application/json");
  http.send(JSON.stringify({
    email,
    key,
    organization,
    encrypted_key: encryptedKey,
  }));
  http.onreadystatechange = (e) => {
    document.getElementById("auth-result").innerHTML = getHttpResult(http);
    if (http.status === 200) {
      document.getElementById("auth-info").innerHTML = `${email} | ${organization}`;
      tokenSession = JSON.parse(http.responseText).token;
      listWorkspaces();
    }
  }
}

const storageKey = "resana-secure-release-tests-key-auth";

function saveAuth() {
  const auth = {};
  let storage = null;
  auth['email'] = document.getElementById("auth-email").value;
  auth['key'] = document.getElementById("auth-key").value;
  auth['organization'] = document.getElementById("auth-organization-id").value;
  auth['encryptedKey'] = document.getElementById("auth-encrypted-key").value;
  auth['password'] = document.getElementById("auth-password").value;
  storage = localStorage.getItem(storageKey) || "[]";
  storage = JSON.parse(storage);
  storage.push(auth);
  localStorage.setItem(storageKey, JSON.stringify(storage));
}

function listAuth() {
  let saves = [];
  const storage = localStorage.getItem(storageKey);
  saves = JSON.parse(storage) || [];
  const modal = document.getElementById("save-modal");
  modal.style.display = "block";
  const listElem = document.getElementById("saves-list");
  listElem.innerHTML = "";
  saves.forEach((save, index) => {
    listElem.innerHTML += `<li onclick="loadAuth(${index})">${save.email} | ${save.key} | ${save.organization}</li>`;
  });
}

function loadAuth(index) {
  const storage = localStorage.getItem(storageKey);
  const saves = JSON.parse(storage) || [];
  document.getElementById("auth-email").value = saves[index].email;
  document.getElementById("auth-key").value = saves[index].key;
  document.getElementById("auth-organization-id").value = saves[index].organization;
  document.getElementById("auth-encrypted-key").value = saves[index].encryptedKey;
  document.getElementById("auth-password").value = saves[index].password;
  const modal = document.getElementById("save-modal");
  modal.style.display = "none";
}

function closeAuthModal() {
  const elem = document.getElementById("save-modal");
  elem.style.display = "none";
}


// LOGOUT
function deconnect(force = false) {
  const http = new XMLHttpRequest();
  http.open("DELETE", "http://localhost:5775/auth");
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send();
  http.onreadystatechange = (e) => {
    document.getElementById("auth-info").innerHTML = "";
    document.getElementById("logout-result").innerHTML = getHttpResult(http);
  }
  openAccount(force);
}

function deconnectAll(force = false) {
  const http = new XMLHttpRequest();
  http.open("DELETE", "http://localhost:5775/auth/all");
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send();
  http.onreadystatechange = (e) => {
    document.getElementById("auth-info").innerHTML = "";
    document.getElementById("logout-result").innerHTML = getHttpResult(http);
  }
  openAccount(force);
}
