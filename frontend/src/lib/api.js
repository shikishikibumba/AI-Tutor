import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
export const api = axios.create({ baseURL: API, withCredentials: true });

api.interceptors.request.use((cfg) => {
  const t = localStorage.getItem("admin_token");
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});

export function errMsg(e) {
  const d = e?.response?.data?.detail;
  if (!d) return e?.message || "Something went wrong";
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join(" ");
  if (d.message) return d.message;
  return JSON.stringify(d);
}

export const pageImageUrl = (docId, page) => `${API}/sources/page-image/${docId}/${page}`;

export async function streamTutor(body, onEvent) {
  const res = await fetch(`${API}/tutor/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const j = await res.json().catch(() => ({}));
    throw new Error(typeof j.detail === "string" ? j.detail : "Tutor request failed");
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop();
    parts.forEach((p) => {
      const line = p.trim();
      if (line.startsWith("data:")) onEvent(JSON.parse(line.slice(5)));
    });
  }
}
