"""Reconocimiento de voz sin conexión (Vosk + modelo en español).

Todo se procesa en el propio equipo: el audio del micrófono nunca sale del
ordenador. Si falta el modelo, Vosk o el micrófono, la aplicación sigue
funcionando y el maestro puede usar el dictado de Windows (tecla Windows + H)
sobre el cuadro de texto.
"""
from __future__ import annotations

import json
import queue
import threading
from pathlib import Path

from .config import model_dirs

FRECUENCIA = 16000


def buscar_modelo() -> Path | None:
    for base in model_dirs():
        if not base.exists():
            continue
        candidatos = [base] + sorted(p for p in base.iterdir() if p.is_dir())
        for c in candidatos:
            if (c / "am").exists() or (c / "conf" / "model.conf").exists():
                return c
    return None


class Dictado:
    def __init__(self):
        self._hilo: threading.Thread | None = None
        self._parar = threading.Event()
        self._lock = threading.Lock()
        self._texto: list[str] = []
        self._parcial = ""
        self._error = ""
        self._modelo = None

    # ------------------------------------------------------------------
    def estado(self) -> dict:
        disponible, motivo = self.disponible()
        with self._lock:
            return {
                "disponible": disponible,
                "motivo": motivo,
                "grabando": bool(self._hilo and self._hilo.is_alive()),
                "texto": " ".join(self._texto),
                "parcial": self._parcial,
                "error": self._error,
            }

    @staticmethod
    def disponible() -> tuple[bool, str]:
        try:
            import vosk  # noqa: F401
        except Exception:
            return False, "El motor de voz (Vosk) no está instalado."
        try:
            import sounddevice  # noqa: F401
        except Exception:
            return False, "No se puede acceder al audio (sounddevice no disponible)."
        if not buscar_modelo():
            return False, "No se encuentra el modelo de voz en español (carpeta «models»)."
        return True, ""

    def iniciar(self) -> dict:
        ok, motivo = self.disponible()
        if not ok:
            raise RuntimeError(motivo)
        if self._hilo and self._hilo.is_alive():
            return self.estado()
        with self._lock:
            self._texto, self._parcial, self._error = [], "", ""
        self._parar.clear()
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._hilo.start()
        return self.estado()

    def detener(self) -> dict:
        self._parar.set()
        if self._hilo:
            self._hilo.join(timeout=5)
        return self.estado()

    # ------------------------------------------------------------------
    def _bucle(self):
        try:
            import sounddevice as sd
            import vosk

            vosk.SetLogLevel(-1)
            if self._modelo is None:
                self._modelo = vosk.Model(str(buscar_modelo()))
            rec = vosk.KaldiRecognizer(self._modelo, FRECUENCIA)
            cola: queue.Queue[bytes] = queue.Queue()

            def callback(indata, frames, time, status):  # noqa: ARG001
                cola.put(bytes(indata))

            with sd.RawInputStream(samplerate=FRECUENCIA, blocksize=8000, dtype="int16",
                                   channels=1, callback=callback):
                while not self._parar.is_set():
                    try:
                        datos = cola.get(timeout=0.3)
                    except queue.Empty:
                        continue
                    if rec.AcceptWaveform(datos):
                        self._añadir(json.loads(rec.Result()).get("text", ""))
                    else:
                        with self._lock:
                            self._parcial = json.loads(rec.PartialResult()).get("partial", "")
            self._añadir(json.loads(rec.FinalResult()).get("text", ""))
        except Exception as e:  # micrófono ocupado, sin permisos, etc.
            with self._lock:
                self._error = f"No se pudo usar el micrófono: {e}"
        finally:
            with self._lock:
                self._parcial = ""

    def _añadir(self, texto: str):
        texto = (texto or "").strip()
        if texto:
            with self._lock:
                self._texto.append(texto)
                self._parcial = ""
