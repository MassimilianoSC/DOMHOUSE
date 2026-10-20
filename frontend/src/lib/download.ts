/** Hands a file to the browser's download, with the given name. */
export function saveFile(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Revoked a little later: some browsers start the download after the click returns.
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}
