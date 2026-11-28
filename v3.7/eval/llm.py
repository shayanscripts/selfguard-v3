"""One chat call to a local model, shared by the eval scripts.

  api="ollama"  Ollama's native /api/chat (default url http://127.0.0.1:11434); records the
                model digest via /api/tags so results say exactly which weights were used.
  api="openai"  any OpenAI-compatible /v1/chat/completions (llama.cpp's llama-server, vLLM,
                Ollama's /v1, ...).

Deterministic settings: temperature 0 and a fixed seed. Retries 3 times with backoff, then
raises.
"""
import http.client
import json
import time
import urllib.error
import urllib.request

DEFAULT_URLS = {"ollama": "http://127.0.0.1:11434", "openai": "http://127.0.0.1:8080"}
BACKOFF = (2.0, 8.0, 30.0)


class LLM:
    def __init__(self, model: str, api: str = "ollama", url: str | None = None, seed: int = 1234,
                 max_tokens: int = 256, timeout: float = 600):
        if api not in DEFAULT_URLS:
            raise ValueError(f"api must be one of {tuple(DEFAULT_URLS)}")
        self.model, self.api, self.seed, self.max_tokens, self.timeout = model, api, seed, max_tokens, timeout
        self.url = (url or DEFAULT_URLS[api]).rstrip("/")
        self.calls = 0

    def _post(self, path: str, body: dict) -> dict:
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.load(r)

    def __call__(self, messages: list[dict], max_tokens: int | None = None) -> str:
        n = max_tokens or self.max_tokens
        if self.api == "ollama":
            path, body = "/api/chat", {"model": self.model, "messages": messages, "stream": False,
                                       "options": {"temperature": 0, "seed": self.seed, "num_predict": n}}
        else:
            path, body = "/v1/chat/completions", {"model": self.model, "messages": messages, "temperature": 0,
                                                  "seed": self.seed, "max_tokens": n}
        for attempt, wait in enumerate((*BACKOFF, None)):
            try:
                d = self._post(path, body)
                self.calls += 1
                if self.api == "ollama":
                    return d["message"]["content"] or ""
                return d["choices"][0]["message"]["content"] or ""
            # OSError covers URLError, timeouts and dropped connections (ConnectionResetError);
            # HTTPException covers RemoteDisconnected and other broken responses
            except (OSError, http.client.HTTPException, KeyError, ValueError):
                if wait is None:
                    raise
                time.sleep(wait)
        return ""

    def describe(self) -> dict:
        """Model name, api, url and (Ollama) the exact digest, for the results file."""
        info = {"model": self.model, "api": self.api, "url": self.url, "seed": self.seed,
                "max_tokens": self.max_tokens}
        if self.api == "ollama":
            try:
                req = urllib.request.Request(self.url + "/api/tags")
                with urllib.request.urlopen(req, timeout=30) as r:
                    tags = json.load(r).get("models", [])
                m = next((t for t in tags if t.get("name") == self.model or t.get("model") == self.model), None)
                if m:
                    info["digest"] = m.get("digest")
                    info["details"] = m.get("details")
            except (OSError, http.client.HTTPException, ValueError):
                info["digest"] = None
        return info
