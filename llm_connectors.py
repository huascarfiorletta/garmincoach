import subprocess
import time
import requests
import signal
import os
from abc import ABC, abstractmethod
from langchain_community.chat_models import ChatOllama
from langchain_core.messages import HumanMessage


class LLMConnector(ABC):
    @abstractmethod
    def ask(self, prompt: str) -> str:
        pass


class OllamaConnector(LLMConnector):
    def __init__(self, model="llama3.2", base_url="http://localhost:11434", manage_server=False):
        self.model = model
        self.base_url = base_url
        self.manage_server = manage_server
        self._server_process = None

        if self.manage_server:
            self._start_server()

        self.llm = ChatOllama(model=self.model, base_url=self.base_url)

    # ── Server lifecycle ───────────────────────────────────────────────────────

    def _is_server_running(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}", timeout=2)
            return r.status_code == 200
        except requests.ConnectionError:
            return False

    def _start_server(self):
        if self._is_server_running():
            print("Ollama already running, skipping launch.")
            return  # don't take ownership of a server we didn't start

        print("Starting Ollama server…")
        self._server_process = subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid,   # own process group so we can kill cleanly
        )

        # Wait up to 10 s for it to become ready
        for _ in range(20):
            if self._is_server_running():
                print("Ollama server ready.")
                return
            time.sleep(0.5)

        raise RuntimeError("Ollama server did not start within 10 seconds.")

    def _stop_server(self):
        if self._server_process is None:
            return
        print("Shutting down Ollama server…")
        os.killpg(os.getpgid(self._server_process.pid), signal.SIGTERM)
        try:
            self._server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(self._server_process.pid), signal.SIGKILL)
        self._server_process = None

    # ── Context manager support ────────────────────────────────────────────────

    def __enter__(self):
        return self

    def __exit__(self, *_):
        if self.manage_server:
            self._stop_server()

    # ── LLM call ──────────────────────────────────────────────────────────────

    def ask(self, prompt: str) -> str:
        response = ""
        # response = self.llm.invoke([HumanMessage(content=prompt)])
        return response.content