let releaseVersion = "vX.Y.Z";

function releaseVersionChange(event) {
  releaseVersion = document.getElementById("release-version").value;
  const elements = document.getElementsByClassName("release-version");
  for (const element of elements) {
    element.innerHTML = releaseVersion;
  }
}
