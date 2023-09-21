// NAV
function openNav() {
  const nav = document.getElementsByTagName("nav")[0];
  if (nav.style.opacity === "") {
    nav.style.display = "block";
    nav.style.opacity = "initial";
  } else {
    nav.style.display = "none";
    nav.style.opacity = "";
  }
}

function openAccount(forceClose = false) {
  const nav = document.getElementById("account-menu");
  if (nav.style.opacity !== "" || forceClose) {
    nav.style.display = "none";
    nav.style.opacity = "";
  } else {
    nav.style.display = "block";
    nav.style.opacity = "initial";
  }
}

const sections = [
  "release",
  "bootstrap",
  "installation",
  "auth",
  "workspace",
  "offline",
  "mount",
  "folder",
  "file",
  "search",
  "invitation",
  "invitation-greeter",
  "invitation-claimer",
  "human",
  "share",
  "recovery",
  "shamir",
  "sequester",
  "logout",
  "result"
];

function navTo(className) {
  sections.forEach(section => {
    const elm = document.getElementById(section);
    elm.style.display = section === className ? "block" : "none";
  });
  openNav();
}


// BOOTSTRAP

const defaultEmail = "gordon.freeman@blackmesa.nm";
const inviteeEmail = "eli.vance@blackmesa.nm";
const defaultPassword = "P@ssw0rd";

function boostrap() {
  const organizationUrl = document.getElementById("bootstrap-url").value;
  const sequesterVerifyKey = document.getElementById("sequester-verify-key").value;
  const http = new XMLHttpRequest();
  http.open("POST", "http://localhost:5775/organization/bootstrap");
  http.setRequestHeader("Content-type", "application/json");
  http.send(JSON.stringify({
    organization_url: organizationUrl,
    email: defaultEmail,
    key: defaultPassword,
    sequester_verify_key: sequesterVerifyKey
  }));
  http.onreadystatechange = (e) => {
    document.getElementById("bootstrap-result").innerHTML = getHttpResult(http);
  }
}

// AUTH
let tokenSession = null;
let authMethod = "password";

function switchAuth() {
  authMethod = authMethod == "key" ? "password" : "key";
  const keyAuth = document.getElementById("key-auth");
  const passwordAuth = document.getElementById("password-auth");
  if (authMethod === "key") {
    keyAuth.style.display = "block";
    passwordAuth.style.display = "none";
  } else {
    keyAuth.style.display = "none";
    passwordAuth.style.display = "block";
  }
}

function login() {
  const keyEmail = document.getElementById("key-email").value;
  const key = document.getElementById("key").value;
  const keyOrganization = document.getElementById("key-organization-id").value;
  const PasswordEmail = document.getElementById("password-email").value;
  const password = document.getElementById("password").value;
  const encryptedKey = document.getElementById("encrypted-key").value;
  const PasswordOrganization = document.getElementById("password-organization-id").value;
  const http = new XMLHttpRequest();
  http.open("POST", "http://localhost:5775/auth");
  http.setRequestHeader("Content-type", "application/json");
  if (authMethod === "key") {
    http.send(JSON.stringify({
      email: keyEmail,
      key,
      organization: keyOrganization
    }));
  } else {
    http.send(JSON.stringify({
      email: PasswordEmail,
      user_password: password,
      encrypted_key: encryptedKey,
      organization: PasswordOrganization
    }));
  }
  http.onreadystatechange = (e) => {
    document.getElementById("auth-result").innerHTML = getHttpResult(http);
    if (http.status === 200) {
      if (authMethod === "key") {
        document.getElementById("auth-info").innerHTML = `${keyEmail} | ${keyOrganization}`;
      } else {
        document.getElementById("auth-info").innerHTML = `${PasswordEmail} | ${PasswordOrganization}`;
      }
      tokenSession = JSON.parse(http.responseText).token;
      listWorkspaces();
    }
  }
}

const saltDerive2 = new Uint8Array("122,205,180,252,110,57,134,101,147,170,189,150,191,228,84,206".split(","));

function getKeyParsecMaterialParsec(passwordACharger) {
  let enc = new TextEncoder();
  return window.crypto.subtle.importKey(
    "raw",
    enc.encode(passwordACharger),
    {name: "PBKDF2"},
    false,
    ["deriveBits", "deriveKey"]
  );
}

async function getKeyParsec(keyMaterial, salt) {
  return window.crypto.subtle.deriveKey(
    {
      "name": "PBKDF2",
      salt: salt,
      "iterations": 100000,
      "hash": "SHA-256"
    },
    keyMaterial,
    { "name": "AES-GCM", "length": 256},
    true,
    [ "encrypt", "decrypt" ]
  );
}

async function derivationPassword(passwordADeriver, saltDerivation) {
  let keyMaterial = await getKeyParsecMaterialParsec(passwordADeriver);
  let key = await getKeyParsec(keyMaterial, saltDerivation);
  return key;
}

async function exportCryptoKey(key) {
  const exported = await window.crypto.subtle.exportKey(
    "raw", key
  );
  const exportedKeyBuffer = new Uint8Array(exported);
  return exportedKeyBuffer;
}

async function deriverPasswordParsec(passwordADeriver) {
  let keyDerive = await derivationPassword(passwordADeriver, saltDerive2);
  keyDerive = await exportCryptoKey(keyDerive);
  return keyDerive;
}

function genererParsecKey() {
  let parsec_key = window.btoa(window.crypto.getRandomValues(new Uint8Array(8)));
  return parsec_key;
}

function importParsecDerivationKey(derivation) {
  return window.crypto.subtle.importKey(
    "raw",
    derivation,
    "AES-GCM",
    true,
    ["encrypt", "decrypt"]
  );
}

function getMessageEncodingParsec(message) {
  let enc = new TextEncoder();
  return enc.encode(message);
}

async function cryptageMessageParsec(keyDerive, message) {
  let iv = window.crypto.getRandomValues(new Uint8Array(12));
  let messageEncapsule = getMessageEncodingParsec(message);
  let ciphertext = await window.crypto.subtle.encrypt(
    {
      name: "AES-GCM",
      iv: iv
    },
    keyDerive,
    messageEncapsule
  );
  let buffer = new Uint8Array(ciphertext);
  return iv.toString()+"/"+buffer.toString();
}

async function crypterParsecKey(parsec_key, passwordADeriver) {
  try{
    let keyDerive = await deriverPasswordParsec(passwordADeriver);
    keyDerive = keyDerive.buffer;
    keyDerive = await importParsecDerivationKey(keyDerive);
    const parsecKeyChiffre = await cryptageMessageParsec(keyDerive, parsec_key);
    return window.btoa(parsecKeyChiffre)
  }
  catch(error){
    if(error?.code){
      return Promise.reject(error)
    }
    return Promise.reject({code: 'crypt-error'})
  }
}

async function generateKey() {
  const password = document.getElementById("generate-password").value;
  const parsecKey = genererParsecKey();
  const encryptedKey = await crypterParsecKey(parsecKey, password);
  document.getElementById("generate-key-result").innerHTML = `
  parsecKey : ${parsecKey}
  encryptedKey : ${encryptedKey}
  `;
}

async function decryptageMessageParsec(keyDerive, message) {
  message = message.split("/");
  let iv = new Uint8Array(message[0].split(","));
  let parsec_key_crypte = message[1];
  let ciphertext = new Uint8Array(parsec_key_crypte.split(",")).buffer;
  let decrypted = await window.crypto.subtle.decrypt(
    {
      name: "AES-GCM",
      iv: iv
    },
    keyDerive,
    ciphertext
  )
  let dec = new TextDecoder();
  return dec.decode(decrypted);
}

async function decryptParsecKey() {
  const password = document.getElementById("generate-password").value;
  let encryptedKey = "==";
  let keyDerive = await deriverPasswordParsec(password);
  keyDerive = keyDerive.buffer;
  keyDerive = await importParsecDerivationKey(keyDerive);
  encryptedKey = window.atob(encryptedKey);
  let parsecKey = await decryptageMessageParsec(keyDerive, encryptedKey);
  return parsecKey;
}

// WORKSPACES
let workspaces = [];

function updateWorkspacesSelect() {
  const elms = document.getElementsByClassName("workspaces-select");
  for (const elm of elms) {
    elm.innerHTML = "";
    elm.innerHTML += `<option value="">Aucun</option>`;
    elm.innerHTML += `<option value="00000000000000000000000000000000">00000000000000000000000000000000</option>`;
    for (const workspace of workspaces) {
      elm.innerHTML += `<option value="${workspace.id}">${workspace.name} | ${workspace.id}</option>`;
    }
  }
}

function createWorkspace() {
  const name = document.getElementById("workspace-name").value;
  const http = new XMLHttpRequest();
  http.open("POST", "http://localhost:5775/workspaces");
  http.setRequestHeader("Content-type", "application/json");
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send(JSON.stringify({
    name
  }));
  http.onreadystatechange = (e) => {
    document.getElementById("workspace-create-result").innerHTML = getHttpResult(http);
    if (http.status === 201) {
      listWorkspaces();
    }
  }
}

function listWorkspaces() {
  const http = new XMLHttpRequest();
  http.open("GET", "http://localhost:5775/workspaces");
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send();
  http.onreadystatechange = (e) => {
    document.getElementById("workspaces-result").innerHTML = getHttpResult(http);
    if (http.status === 200) {
      workspaces = JSON.parse(http.response).workspaces;
      updateWorkspacesSelect();
    }
  }
}

function renameWorkspace() {
  const workspaceID = document.getElementById("workspace-rename-id").value;
  const oldName = document.getElementById("workspace-rename-old-name").value;
  const newName = document.getElementById("workspace-rename-new-name").value;
  const http = new XMLHttpRequest();
  http.open("PATCH", `http://localhost:5775/workspaces/${workspaceID}`);
  http.setRequestHeader("Content-type", "application/json");
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send(JSON.stringify({
    old_name: oldName,
    new_name: newName
  }));
  http.onreadystatechange = (e) => {
    document.getElementById("workspace-rename-result").innerHTML = getHttpResult(http);
  }
}

// OFFLINE AVAILABILITY
function checkOffline() {
  const workspace = document.getElementById("offine-workspace").value;
  http.open("GET", `http://localhost:5775/workspaces/${workspace}/get_offline_availability_status`);
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send();
  http.onreadystatechange = (e) => {
    document.getElementById("offine-get-result").innerHTML = getHttpResult(http);
  }
}

// MOUNT/UNMOUNT
function mountWorkspace() {
  // TODO timestamped workspace json={"timestamp": timestamp}
  const workspace = document.getElementById("mount-workspace").value;
  http.open("POST", `http://localhost:5775/workspaces/${workspace}/mount`);
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send();
  http.onreadystatechange = (e) => {
    document.getElementById("mount-workspace-result").innerHTML = getHttpResult(http);
  }
}

function unmountWorkspace() {
  // TODO timestamped workspace json={"timestamp": timestamp}
  const workspace = document.getElementById("unmount-workspace").value;
  http.open("POST", `http://localhost:5775/workspaces/${workspace}/unmount`);
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send();
  http.onreadystatechange = (e) => {
    document.getElementById("unmount-workspace-result").innerHTML = getHttpResult(http);
  }
}

function listMountpoints() {
  // TODO timestamped workspace json={"timestamp": timestamp}
  http.open("GET", `http://localhost:5775/workspaces/mountpoints`);
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send();
  http.onreadystatechange = (e) => {
    document.getElementById("unmount-workspace-result").innerHTML = getHttpResult(http);
  }
}

// FOLDER
let folders = []
let workspaceID = null;

function updateFoldersSelect() {
  const elms = document.getElementsByClassName("folders-select");
  for (const elm of elms) {
    elm.innerHTML = "";
    elm.innerHTML += `<option value="">Aucun</option>`;
    elm.innerHTML += `<option value="00000000000000000000000000000000">00000000000000000000000000000000</option>`;
    for (const folder of folders) {
      elm.innerHTML += `<option value="${folder.id}">${folder.name} | ${folder.id}</option>`;
    }
  }
}

function createFolder() {
  const workspace = document.getElementById("workspace-folders-list-id").value;
  const parent = document.getElementById("folder-parent").value;
  const name = document.getElementById("folder-name").value;
  const http = new XMLHttpRequest();
  http.open("POST", `http://localhost:5775/workspaces/${workspace}/folders`);
  http.setRequestHeader("Content-type", "application/json");
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send(JSON.stringify({
    name,
    parent
  }));
  http.onreadystatechange = (e) => {
    document.getElementById("folder-create-result").innerHTML = getHttpResult(http);
    if (http.status === 201) {
      listFolders();
    }
  }
}

function parseFolderNode(node, path = "") {
  let result = [];
  let fullPath = path + node.name;
  fullPath = fullPath.endsWith("/") ? fullPath : fullPath + "/";
  result.push({ id: node.id, name: fullPath });
  if (node.children) {
    for (const [key, value] of Object.entries(node.children)) {
      result = result.concat(parseFolderNode(value, fullPath));
    }
  }
  return result;
}

function listFolders(fromFile = false) {
  let workspace = document.getElementById("workspace-folders-list-id").value;
  if (fromFile) {
    workspace = document.getElementById("workspace-files-list-id").value;
  }
  const http = new XMLHttpRequest();
  http.open("GET", `http://localhost:5775/workspaces/${workspace}/folders`);
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send();
  http.onreadystatechange = (e) => {
    document.getElementById("folders-result").innerHTML = getHttpResult(http);
    if (http.status === 200) {
      const root = JSON.parse(http.response);
      folders = parseFolderNode(root);
      updateFoldersSelect();
    }
  }
}

function renameFolder() {
  const workspace = document.getElementById("workspace-folders-list-id").value;
  const id = document.getElementById("rename-folder-id").value;
  const newName = document.getElementById("rename-folder-name").value;
  const newParent = document.getElementById("rename-folder-parent").value;
  const http = new XMLHttpRequest();
  http.open("POST", `http://localhost:5775/workspaces/${workspace}/folders/rename`);
  http.setRequestHeader("Content-type", "application/json");
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send(JSON.stringify({
    id,
    new_name: newName,
    new_parent: newParent
  }));
  http.onreadystatechange = (e) => {
    document.getElementById("rename-folder-result").innerHTML = getHttpResult(http);
    if (http.status === 200) {
      listFolders();
    }
  }
}

function deleteFolder() {
  const workspace = document.getElementById("workspace-folders-list-id").value;
  const folder = document.getElementById("delete-folder-input").value;
  const http = new XMLHttpRequest();
  http.open("DELETE", `http://localhost:5775/workspaces/${workspace}/folders/${folder}`);
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send();
  http.onreadystatechange = (e) => {
    document.getElementById("delete-folder-result").innerHTML = getHttpResult(http);
    if (http.status === 200) {
      listFolders();
    }
  }
}

// FILE
let files = [];
let smallFileContent = "";
const smallFileSize = 1024;
const largeFileSize = 2**20 * 20  // 20mB

function loadSmallFile(e) {
  const file = e.target.files[0];
  if (!file) {
    return;
  }
  const reader = new FileReader();
  reader.readAsDataURL(file);
  reader.onload = function(e) {
    smallFileContent = e.target.result.split(",")[1];
  }
}

function loadLargeFile(e) {
  console.log(e);
}

document.getElementById('small-file').addEventListener('change', loadSmallFile, false);
document.getElementById('large-file').addEventListener('change', loadLargeFile, false);

function updateFilesSelect() {
  const elms = document.getElementsByClassName("files-select");
  for (const elm of elms) {
    elm.innerHTML = "";
    elm.innerHTML += `<option value="">Aucun</option>`;
    elm.innerHTML += `<option value="00000000000000000000000000000000">00000000000000000000000000000000</option>`;
    for (const file of files) {
      elm.innerHTML += `<option value="${file.id}">${file.name} | ${file.id}</option>`;
    }
  }
}

function createSmallFile() {
  const workspace = document.getElementById("workspace-files-list-id").value;
  const parent = document.getElementById("folder-file-list-id").value;
  const name = document.getElementById("small-filename").value;
  // const fileContent = random.randbytes(smallFileSize);
  const http = new XMLHttpRequest();
  http.open("POST", `http://localhost:5775/workspaces/${workspace}/files`);
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.setRequestHeader("Content-type", "application/json");
  http.send(JSON.stringify({
    name,
    parent,
    content: smallFileContent
  }));
  http.onreadystatechange = (e) => {
    document.getElementById("create-small-file-result").innerHTML = getHttpResult(http);
  }
}

function createLargeFile() {
  const workspace = document.getElementById("workspace-files-list-id").value;
  const parent = document.getElementById("folder-file-list-id").value;
  const name = document.getElementById("large-filename").value;
  // const fileContent = random.randbytes(largeFileSize);
  const formData = new FormData();
  formData.append("data", JSON.stringify({parent}));
  formData.append("files");
  const http = new XMLHttpRequest();
  http.open("POST", `http://localhost:5775/workspaces/${workspace}/files`);
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send(JSON.stringify({
    name,
    parent,
    content: ""
  }));
  http.onreadystatechange = (e) => {
    document.getElementById("create-large-file-result").innerHTML = getHttpResult(http);
  }
}

function listFiles() {
  const workspace = document.getElementById("workspace-files-list-id").value;
  const folder = document.getElementById("folder-file-list-id").value;
  const http = new XMLHttpRequest();
  http.open("GET", `http://localhost:5775/workspaces/${workspace}/files/${folder}`);
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send();

  http.onreadystatechange = (e) => {
    document.getElementById("files-result").innerHTML = getHttpResult(http);
    if (http.status === 200) {
      files = JSON.parse(http.responseText).files;
      updateFilesSelect();
    }
  }
}

function openFile() {
  const workspace = document.getElementById("workspace-files-list-id").value;
  const fileID = document.getElementById("open-file-id").value;
  const http = new XMLHttpRequest();
  http.open("POST", `http://localhost:5775/workspaces/${workspace}/open/${fileID}`);
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send();

  http.onreadystatechange = (e) => {
    document.getElementById("open-file-result").innerHTML = getHttpResult(http);
  }
}

function renameFile() {
  const workspace = document.getElementById("workspace-files-list-id").value;
  const id = document.getElementById("file-id-input").value;
  const newName = document.getElementById("file-id-input").value;
  const newParent = document.getElementById("file-id-input").value;
  const http = new XMLHttpRequest();
  http.open("POST", `http://localhost:5775/workspaces/${workspace}/files/rename`);
  http.setRequestHeader("Content-type", "application/json");
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send(JSON.stringify({
    id,
    new_name: newName,
    new_parent: newParent
  }));
  http.onreadystatechange = (e) => {
    document.getElementById("rename-file-result").innerHTML = getHttpResult(http);
  }
}

function deleteFiles() {
  const workspace = document.getElementById("workspace-input").value;
  for (const fileId of files) {
    const http = new XMLHttpRequest();
    http.open("DELETE", `http://localhost:5775/workspaces/${workspace}/files/${fileId}`);
    http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
    http.send();
    http.onreadystatechange = (e) => {
      document.getElementById("delete-result").innerHTML = getHttpResult(http);
    }
  }
}

// INVITATION
function updateInvitationsSelect(usersInvitations, deviceInvitation) {
  const elms = document.getElementsByClassName("invitations-select");
  for (const elm of elms) {
    elm.innerHTML = "";
    elm.innerHTML += `<option value="">Aucun</option>`;
    elm.innerHTML += `<option value="00000000000000000000000000000000">00000000000000000000000000000000</option>`;
    for (const invitation of usersInvitations) {
      elm.innerHTML += `<option value="${invitation.token}">${invitation.claimer_email} | ${invitation.token}</option>`;
    }
    if (deviceInvitation) {
      elm.innerHTML += `<option value="${deviceInvitation.token}">Device | ${deviceInvitation.token}</option>`;
    }
  }
}

function createInvitation() {
  const email = document.getElementById("claimer-email").value;
  const http = new XMLHttpRequest();
  http.open("POST", "http://localhost:5775/invitations");
  http.setRequestHeader("Content-type", "application/json");
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send(JSON.stringify({
    type: "user",
    claimer_email: email
  }));
  http.onreadystatechange = (e) => {
    document.getElementById("create-invitation-result").innerHTML = getHttpResult(http);
    if (http.status === 200) {
      listInvitations();
    }
  }
}

function createInvitationDevice() {
  const http = new XMLHttpRequest();
  http.open("POST", "http://localhost:5775/invitations");
  http.setRequestHeader("Content-type", "application/json");
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send(JSON.stringify({
    type: "device"
  }));
  http.onreadystatechange = (e) => {
    document.getElementById("create-invitation-device-result").innerHTML = getHttpResult(http);
    if (http.status === 200) {
      listInvitations();
    }
  }
}

function listInvitations() {
  const http = new XMLHttpRequest();
  http.open("GET", "http://localhost:5775/invitations");
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send();
  http.onreadystatechange = (e) => {
    document.getElementById("invitations-result").innerHTML = getHttpResult(http);
    if (http.status === 200) {
      const usersInvitations = JSON.parse(http.response).users;
      const deviceInvitation = JSON.parse(http.response).device;
      updateInvitationsSelect(usersInvitations, deviceInvitation);
    }
  }
}

function deleteInvitation() {
  const invitationToken = document.getElementById("delete-invitation-token").value;
  const http = new XMLHttpRequest();
  http.open("DELETE", `http://localhost:5775/invitations/${invitationToken}`);
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send();
  http.onreadystatechange = (e) => {
    document.getElementById("delete-invitation-result").innerHTML = getHttpResult(http);
    if (http.status === 204) {
      listInvitations();
    }
  }
}

function claimerRetreiveInfo() {
  const invitationToken = document.getElementById("claimer-invitation-token").value;
  const http = new XMLHttpRequest();
  http.open("POST", `http://localhost:5775/invitations/${invitationToken}/claimer/0-retreive-info`);
  http.setRequestHeader("Content-type", "application/json");
  http.send(JSON.stringify({}));
  http.onreadystatechange = (e) => {
    document.getElementById("claimer-retreive-info-result").innerHTML = getHttpResult(http);
  }
}

function claimerWaitPeerReady() {
  const invitationToken = document.getElementById("claimer-invitation-token").value;
  const http = new XMLHttpRequest();
  http.open("POST", `http://localhost:5775/invitations/${invitationToken}/claimer/1-wait-peer-ready`);
  http.setRequestHeader("Content-type", "application/json");
  http.send(JSON.stringify({}));
  http.onreadystatechange = (e) => {
    document.getElementById("claimer-wait-peer-ready-result").innerHTML = getHttpResult(http);
  }
}

function claimerCheckTrust() {
  const invitationToken = document.getElementById("claimer-invitation-token").value;
  const greeterSAS = document.getElementById("greeter-sas").value;
  const http = new XMLHttpRequest();
  http.open("POST", `http://localhost:5775/invitations/${invitationToken}/claimer/2-check-trust`);
  http.setRequestHeader("Content-type", "application/json");
  http.send(JSON.stringify({
    greeter_sas: greeterSAS
  }));
  http.onreadystatechange = (e) => {
    document.getElementById("claimer-check-trust-result").innerHTML = getHttpResult(http);
  }
}

function claimerWaitPeerTrust() {
  const invitationToken = document.getElementById("claimer-invitation-token").value;
  const http = new XMLHttpRequest();
  http.open("POST", `http://localhost:5775/invitations/${invitationToken}/claimer/3-wait-peer-trust`);
  http.setRequestHeader("Content-type", "application/json");
  http.send(JSON.stringify({}));
  http.onreadystatechange = (e) => {
    document.getElementById("claimer-wait-peer-trust-result").innerHTML = getHttpResult(http);
  }
}

function claimerFinalize() {
  const invitationToken = document.getElementById("claimer-invitation-token").value;
  const key = document.getElementById("claimer-key").value;
  const http = new XMLHttpRequest();
  http.open("POST", `http://localhost:5775/invitations/${invitationToken}/claimer/4-finalize`);
  http.setRequestHeader("Content-type", "application/json");
  http.send(JSON.stringify({ key }));
  http.onreadystatechange = (e) => {
    document.getElementById("claimer-finalize-result").innerHTML = getHttpResult(http);
  }
}

function greeterWaitPeerReady() {
  const invitationToken = document.getElementById("greeter-invitation-token").value;
  const http = new XMLHttpRequest();
  http.open("POST", `http://localhost:5775/invitations/${invitationToken}/greeter/1-wait-peer-ready`);
  http.setRequestHeader("Content-type", "application/json");
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send(JSON.stringify({}));
  http.onreadystatechange = (e) => {
    document.getElementById("greeter-wait-peer-ready-result").innerHTML = getHttpResult(http);
  }
}

function greeterCheckTrust() {
  const invitationToken = document.getElementById("greeter-invitation-token").value;
  const http = new XMLHttpRequest();
  http.open("POST", `http://localhost:5775/invitations/${invitationToken}/greeter/2-wait-peer-trust`);
  http.setRequestHeader("Content-type", "application/json");
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send(JSON.stringify({}));
  http.onreadystatechange = (e) => {
    document.getElementById("greeter-check-trust-result").innerHTML = getHttpResult(http);
  }
}

function greeterWaitPeerTrust() {
  const invitationToken = document.getElementById("greeter-invitation-token").value;
  const claimerSAS = document.getElementById("claimer-sas").value;
  const http = new XMLHttpRequest();
  http.open("POST", `http://localhost:5775/invitations/${invitationToken}/greeter/3-check-trust`);
  http.setRequestHeader("Content-type", "application/json");
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send(JSON.stringify({
    claimer_sas: claimerSAS
  }));
  http.onreadystatechange = (e) => {
    document.getElementById("greeter-wait-peer-trust-result").innerHTML = getHttpResult(http);
  }
}

function greeterFinalize() {
  const invitationToken = document.getElementById("greeter-invitation-token").value;
  const grantedProfile = document.getElementById("granted-profile").value || null;
  const email = document.getElementById("greeter-claimer-email").value;
  const http = new XMLHttpRequest();
  http.open("POST", `http://localhost:5775/invitations/${invitationToken}/greeter/4-finalize`);
  http.setRequestHeader("Content-type", "application/json");
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send(JSON.stringify({
    claimer_email: email,
    granted_profile: grantedProfile
  }));
  http.onreadystatechange = (e) => {
    document.getElementById("greeter-finalize-result").innerHTML = getHttpResult(http);
  }
}

// HUMANS

function updateHumansSelect(humans) {
  const elms = document.getElementsByClassName("humans-select");
  for (const elm of elms) {
    elm.innerHTML = "";
    elm.innerHTML += `<option value="">Aucun</option>`;
    elm.innerHTML += `<option value="donotexist@donotexist.com">donotexist@donotexist.com</option>`;
    for (const human of humans) {
      elm.innerHTML += `<option value="${human.human_handle.email}">${human.human_handle.email}</option>`;
    }
  }
}

function getHumans() {
  const http = new XMLHttpRequest();
  http.open("GET", "http://localhost:5775/humans");
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send();
  http.onreadystatechange = (e) => {
    document.getElementById("humans-result").innerHTML = getHttpResult(http);
    if (http.status === 200) {
      updateHumansSelect(JSON.parse(http.response).users);
    }
  }
}

function revoke() {
  const email = document.getElementById("revoke-email").value;
  const http = new XMLHttpRequest();
  http.open("POST", `http://localhost:5775/humans/${email}/revoke`);
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send();
  http.onreadystatechange = (e) => {
    document.getElementById("revoke-result").innerHTML = getHttpResult(http);
  }
}

// SHARE
function share() {
  const workspace = document.getElementById("share-workspace").value;
  const email = document.getElementById("share-email").value;
  const role = document.getElementById("share-role").value || null;
  const http = new XMLHttpRequest();
  http.open("PATCH", `http://localhost:5775/workspaces/${workspace}/share`);
  http.setRequestHeader("Content-type", "application/json");
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send(JSON.stringify({
    email,
    role
  }));
  http.onreadystatechange = (e) => {
    document.getElementById("share-result").innerHTML = getHttpResult(http);
  }
}

function listShares() {
  const workspace = document.getElementById("share-workspace").value;
  const http = new XMLHttpRequest();
  http.open("GET", `http://localhost:5775/workspaces/${workspace}/share`);
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send();
  http.onreadystatechange = (e) => {
    document.getElementById("shares-result").innerHTML = getHttpResult(http);
  }
}

// RECOVERY
function exportRecovery() {
  const http = new XMLHttpRequest();
  http.open("POST", `http://localhost:5775/recovery/export`);
  http.setRequestHeader("Content-type", "application/json");
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send(JSON.stringify({}));
  http.onreadystatechange = (e) => {
    document.getElementById("export-result").innerHTML = getHttpResult(http);
  }
}

function importRecovery() {
  const workspace = document.getElementById("workspace").value;
  const recoveryDeviceFileContent = "";
  const recoveryDevicePassphrase = "";
  const http = new XMLHttpRequest();
  http.open("POST", `http://localhost:5775/recovery/import`);
  http.setRequestHeader("Content-type", "application/json");
  http.send(JSON.stringify({
    recovery_device_file_content: recoveryDeviceFileContent,
    recovery_device_passphrase: recoveryDevicePassphrase
  }));
  http.onreadystatechange = (e) => {
    document.getElementById("import-result").innerHTML = getHttpResult(http);
  }
}


// SHAMIR
function shamirSetup() {
  const http = new XMLHttpRequest();
  http.open("POST", `http://localhost:5775/recovery/shamir/setup`);
  http.setRequestHeader("Content-type", "application/json");
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send(JSON.stringify({
    threshold: 0,
    recipients: [{
      email: "",
      weight: 1
    }]
  }));
  http.onreadystatechange = (e) => {
    document.getElementById("shamir-setup-result").innerHTML = getHttpResult(http);
  }
}

function shamirDelete() {
  const http = new XMLHttpRequest();
  http.open("DELETE", `http://localhost:5775/recovery/shamir/setup`);
  http.setRequestHeader("Content-type", "application/json");
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send(JSON.stringify({}));
  http.onreadystatechange = (e) => {
    document.getElementById("shamir-delete-result").innerHTML = getHttpResult(http);
  }
}

function shamirGetCurrent() {
  const http = new XMLHttpRequest();
  http.open("GET", `http://localhost:5775/recovery/shamir/setup`);
  http.setRequestHeader("Content-type", "application/json");
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send(JSON.stringify({}));
  http.onreadystatechange = (e) => {
    document.getElementById("shamir-get-current-result").innerHTML = getHttpResult(http);
  }
}

function shamirGetOthers() {
  const http = new XMLHttpRequest();
  http.open("GET", `http://localhost:5775/recovery/shamir/setup/others`);
  http.setRequestHeader("Content-type", "application/json");
  http.setRequestHeader("Authorization", `bearer ${tokenSession}`);
  http.send(JSON.stringify({}));
  http.onreadystatechange = (e) => {
    document.getElementById("shamir-get-others-result").innerHTML = getHttpResult(http);
  }
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

const keyAuthStorageKey = "resana-secure-release-tests-key-auth";
const passwordAuthStorageKey = "resana-secure-release-tests-password-auth";

function saveAuth() {
  const auth = {};
  let storage = null;
  if (authMethod === "key") {
    auth['email'] = document.getElementById("key-email").value;
    auth['key'] = document.getElementById("key").value;
    auth['organization'] = document.getElementById("key-organization-id").value;
  } else {
    auth['email'] = document.getElementById("password-email").value;
    auth['password'] = document.getElementById("password").value;
    auth['encryptedKey'] = document.getElementById("encrypted-key").value;
    auth['organization'] = document.getElementById("password-organization-id").value;
  }
  const storageKey = authMethod === "key" ? keyAuthStorageKey : passwordAuthStorageKey;
  storage = localStorage.getItem(storageKey) || "[]";
  storage = JSON.parse(storage);
  storage.push(auth);
  localStorage.setItem(storageKey, JSON.stringify(storage));
}

function listAuth() {
  const storageKey = authMethod === "key" ? keyAuthStorageKey : passwordAuthStorageKey;
  let saves = [];
  const storage = localStorage.getItem(storageKey);
  saves = JSON.parse(storage) || [];
  const modal = document.getElementById("save-modal");
  modal.style.display = "block";
  const listElem = document.getElementById("saves-list");
  listElem.innerHTML = "";
  saves.forEach((save, index) => {
    if (authMethod === "key") {
      listElem.innerHTML += `<li onclick="loadAuth(${index})">${save.email} | ${save.key} | ${save.organization}</li>`;
    } else {
      listElem.innerHTML += `<li onclick="loadAuth(${index})">${save.email} | ${save.password} | ${save.organization}</li>`;
    }
  });
}

function loadAuth(index) {
  const storageKey = authMethod === "key" ? keyAuthStorageKey : passwordAuthStorageKey;
  const storage = localStorage.getItem(storageKey);
  const saves = JSON.parse(storage) || [];
  if (authMethod === "key") {
    document.getElementById("key-email").value = saves[index].email;
    document.getElementById("key").value = saves[index].key;
    document.getElementById("key-organization-id").value = saves[index].organization;
  } else {
    document.getElementById("password-email").value = saves[index].email;
    document.getElementById("password").value = saves[index].password;
    document.getElementById("encrypted-key").value = saves[index].encryptedKey;
    document.getElementById("password-organization-id").value = saves[index].organization;
  }
  const modal = document.getElementById("save-modal");
  modal.style.display = "none";
}

function closeAuthModal() {
  const elem = document.getElementById("save-modal");
  elem.style.display = "none";
}

// RESULT

(function() {
  switchAuth();
})();
