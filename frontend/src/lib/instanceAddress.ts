/**
 * The address of an apartment's engine as the server calls it (bff/instances.py base_url, P-83 T3d-5): the port is
 * added after the host only when the address does not already have one; a demonstration engine (mock://) has no port.
 */
export function instanceAddress(url: string, port: number | null | undefined): string {
  const v = url.trim();
  if (!port || v.toLowerCase().startsWith("mock://")) return v;
  const schemeEnd = v.indexOf("://");
  const start = schemeEnd >= 0 ? schemeEnd + 3 : 0;
  const rest = v.slice(start);
  const cut = rest.search(/[/?#]/);
  const host = cut >= 0 ? rest.slice(0, cut) : rest;
  if (host.includes(":")) return v;
  return `${v.slice(0, start)}${host}:${port}${cut >= 0 ? rest.slice(cut) : ""}`;
}
