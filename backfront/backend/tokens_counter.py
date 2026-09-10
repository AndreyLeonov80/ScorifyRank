# python3 tokens_counter.py /Users/aiapi/Desktop/gramlead/code/pre-prod-1/backfront/out/
# или конкретный файл:
# python3 tokens_counter.py /Users/aiapi/Desktop/gramlead/code/pre-prod-1/backfront/out/somefile.jsonl


#!/usr/bin/env python3
# coding: utf-8
"""
tokens_counter_oop.py

Версия: записывает:
- <filename>-tokens.txt (overwrite) — строки "date_utc | name | text"
- <filename>-tokens.json (replace) — структурированный JSON
- <filename>-tokens-calculated.txt (replace) — содержит только одно число:
    суммарное количество токенов по выбранной модели (по умолчанию первая модель в Config.MODELS)

Конфигурация в классе Config.
"""

from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import sys
import traceback

# Попытки импортировать реальные токенайзеры
try:
    import tiktoken  # type: ignore
except Exception:
    tiktoken = None  # type: ignore

try:
    from transformers import AutoTokenizer  # type: ignore
except Exception:
    AutoTokenizer = None  # type: ignore


# ---------------------------
# Конфигурация (правь здесь)
# ---------------------------
class Config:
    # Суффиксы / имена выходных файлов (добавятся к stem исходного файла)
    TOKENS_TXT_SUFFIX = "-tokens.txt"               # overwrite
    TOKENS_JSON_SUFFIX = "-tokens.json"             # replace
    TOKENS_CALC_SUFFIX = "-tokens-calculated.txt"  # replace, будет содержать только одно число

    # Список моделей, для которых считаем токены (можно добавить свои имена)
    MODELS = [
        "yandexgpt-5-lite-8b-instruct",
        "T-lite-instruct"
    ]

    # Модель, для которой записываем итоговое число в TOKENS_CALC_SUFFIX.
    # Если None — используется MODELS[0] (первая модель).
    TOKENS_CALC_MODEL: Optional[str] = None

    # Поведение: если True — пропускать записи без текста; False — сохранять с "null"
    SKIP_EMPTY_TEXT = False

    # Кодировка файлов
    ENCODING = "utf-8"


# ---------------------------
# Чтение JSONL и извлечение полей
# ---------------------------
class JsonlReader:
    def __init__(self, path: Path, config: Config):
        self.path = path
        self.config = config

    def read_messages(self) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        with self.path.open("r", encoding=self.config.ENCODING) as fh:
            for idx, raw in enumerate(fh, start=1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    print(f"[WARN] Некорректный JSON в {self.path}:{idx} — пропускаю")
                    continue

                name = self._deep_get(obj, ["sender", "name"]) \
                       or self._deep_get(obj, ["sender", "username"]) \
                       or self._deep_get(obj, ["chat", "title"])
                text = self._deep_get(obj, ["message", "text"]) \
                       or self._deep_get(obj, ["text"])
                date_utc = self._deep_get(obj, ["message", "date_utc"]) \
                           or self._deep_get(obj, ["date_utc"]) \
                           or self._deep_get(obj, ["message", "date"])

                name = name if isinstance(name, str) else None
                text = text if isinstance(text, str) else None
                date_utc = date_utc if isinstance(date_utc, str) else None

                if self.config.SKIP_EMPTY_TEXT and (not text):
                    continue

                # порядок: date_utc | name | text
                combined_line = " | ".join([(date_utc or "null"), (name or "null"), (text or "null")])

                messages.append({
                    "name": name,
                    "text": text,
                    "date_utc": date_utc,
                    "combined": combined_line,
                    "raw": obj
                })
        return messages

    @staticmethod
    def _deep_get(d: dict, keys: List[str]):
        cur = d
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                return None
            cur = cur[k]
        return cur


# ---------------------------
# Запись tokens.txt (overwrite)
# ---------------------------
class TokensTxtWriter:
    def __init__(self, suffix: str, config: Config):
        self.suffix = suffix
        self.config = config

    def write(self, src_path: Path, messages: List[Dict[str, Any]]) -> Path:
        out_path = src_path.with_name(src_path.stem + self.suffix)
        # Режим "w" — перезаписываем файл (overwrite)
        with out_path.open("w", encoding=self.config.ENCODING) as fh:
            for msg in messages:
                fh.write(msg.get("combined", "null") + "\n")
        print(f"[INFO] Wrote {len(messages)} lines (overwrite) to {out_path}")
        return out_path


# ---------------------------
# Абстракция подсчёта токенов
# ---------------------------
class TokenizerProvider:
    def __init__(self):
        self._cache: Dict[str, Any] = {}

    def count_tokens(self, text: str, model: str) -> int:
        text = text or ""
        # 1) tiktoken (если доступен)
        try:
            if tiktoken is not None:
                enc = tiktoken.get_encoding("gpt2")
                return len(enc.encode(text))
        except Exception:
            pass

        # 2) transformers (если доступен)
        try:
            if AutoTokenizer is not None:
                key = "gpt2"
                if key not in self._cache:
                    tok = AutoTokenizer.from_pretrained("gpt2", use_fast=True)
                    self._cache[key] = tok
                tok = self._cache[key]
                ids = tok.encode(text, add_special_tokens=False)
                return len(ids)
        except Exception:
            pass

        # 3) Fallback approximation
        b = text.encode("utf-8")
        approx = max(0, len(b) // 4)
        return approx


# ---------------------------
# Формирование JSON и tokens-calculated.txt (только число)
# ---------------------------
class Reporter:
    def __init__(self, config: Config, tokenizer: TokenizerProvider):
        self.config = config
        self.tokenizer = tokenizer

    def write_json(self, src_path: Path, messages: List[Dict[str, Any]]) -> Path:
        out = {
            "source": str(src_path),
            "total_messages": len(messages),
            "messages": [
                {
                    "date_utc": m.get("date_utc"),
                    "name": m.get("name"),
                    "text": m.get("text"),
                    "combined": m.get("combined")
                } for m in messages
            ]
        }
        out_path = src_path.with_name(src_path.stem + self.config.TOKENS_JSON_SUFFIX)
        with out_path.open("w", encoding=self.config.ENCODING) as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
        print(f"[INFO] Wrote structured JSON to {out_path}")
        return out_path

    def write_calculated(self, src_path: Path, messages: List[Dict[str, Any]]) -> Path:
        """
        Записывает только одно число в файл <filename>-tokens-calculated.txt:
        суммарное количество токенов для выбранной модели.
        """
        # Определяем модель для подсчёта: либо явно в конфиге, либо первая в MODELS
        model = self.config.TOKENS_CALC_MODEL or (self.config.MODELS[0] if self.config.MODELS else None)
        if model is None:
            raise ValueError("No model specified for token calculation (Config.TOKENS_CALC_MODEL or Config.MODELS)")

        total_tokens = 0
        # Подсчёт на основе combined (date_utc | name | text). при желании можно считать по text — поменяй m.get("text","")
        for m in messages:
            combined = m.get("combined", "") or ""
            cnt = self.tokenizer.count_tokens(combined, model)
            total_tokens += cnt

        out_path = src_path.with_name(src_path.stem + self.config.TOKENS_CALC_SUFFIX)
        # Записываем только число (как ascii текст), перезаписывая файл
        with out_path.open("w", encoding=self.config.ENCODING) as fh:
            fh.write(str(total_tokens) + "\n")

        print(f"[INFO] Wrote total token count ({total_tokens}) for model '{model}' to {out_path}")
        return out_path


# ---------------------------
# CLI приложение
# ---------------------------
class CliApp:
    def __init__(self):
        self.config = Config()
        self.args = self._parse_args()
        self.tokenizer = TokenizerProvider()
        self.reporter = Reporter(self.config, self.tokenizer)
        self.writer = TokensTxtWriter(self.config.TOKENS_TXT_SUFFIX, self.config)

    def _parse_args(self):
        p = argparse.ArgumentParser(description="Process .jsonl -> overwrite tokens.txt, create tokens.json, and tokens-calculated.txt (single number)")
        p.add_argument("path", type=str, help="Path to .jsonl file or directory")
        return p.parse_args()

    def run(self):
        path = Path(self.args.path).expanduser().resolve()
        if not path.exists():
            print(f"[ERROR] Path not found: {path}")
            sys.exit(2)

        targets: List[Path] = []
        if path.is_file() and path.suffix == ".jsonl":
            targets = [path]
        elif path.is_dir():
            targets = sorted([p for p in path.iterdir() if p.suffix == ".jsonl"])
        else:
            print(f"[ERROR] Provided path is neither a .jsonl file nor a directory with .jsonl files: {path}")
            sys.exit(2)

        if not targets:
            print(f"[INFO] No .jsonl files found at {path}")
            return

        for f in targets:
            try:
                print(f"[INFO] Processing {f}")
                reader = JsonlReader(f, self.config)
                messages = reader.read_messages()
                # overwrite tokens.txt (date_utc | name | text)
                self.writer.write(f, messages)
                # write structured JSON (replace)
                self.reporter.write_json(f, messages)
                # write only total token count (replace)
                self.reporter.write_calculated(f, messages)
            except Exception as e:
                print(f"[ERROR] Exception while processing {f}: {e}")
                traceback.print_exc()


def main():
    try:
        CliApp().run()
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    main()
