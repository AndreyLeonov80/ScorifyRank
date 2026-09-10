# === Настройки ===
OUT_DIR = "out"
TEMPLATE_DIR = "templates"
TEMPLATE_NAME = "default.tpl"
TOKENS_SUFFIX = "-tokens-calculated.txt"
HTML_SUFFIX = "-llm.html"
# =================

import sys
from pathlib import Path

class LLMDocumentProcessor:
    def __init__(self, out_dir=OUT_DIR, template_dir=TEMPLATE_DIR, template_name=TEMPLATE_NAME):
        self.out_dir = Path(out_dir)
        self.template_path = Path(template_dir) / template_name
        self.tokens_suffix = TOKENS_SUFFIX
        self.html_suffix = HTML_SUFFIX
        self._load_template()

    def _load_template(self):
        if not self.template_path.exists():
            print(f"Ошибка: шаблон не найден — {self.template_path}", file=sys.stderr)
            sys.exit(1)
        with open(self.template_path, "r", encoding="utf-8") as f:
            self.template_content = f.read()

    def get_tokens(self, filename_base: str) -> str:
        """Читает первую непустую строку из <filename>-tokens-calculated.txt."""
        tokens_file = self.out_dir / f"{filename_base}{self.tokens_suffix}"
        if not tokens_file.exists():
            return "0"

        try:
            with open(tokens_file, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped:
                        return stripped
            return "0"
        except Exception as e:
            print(f"Ошибка при чтении {tokens_file}: {e}", file=sys.stderr)
            return "0"

    def process_file(self, jsonl_path: Path):
        filename_base = jsonl_path.stem
        html_path = self.out_dir / f"{filename_base}{self.html_suffix}"

        # Создаём HTML, если его нет
        if not html_path.exists():
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(self.template_content)
            print(f"Создан: {html_path}")

        # Подставляем актуальное значение токенов
        tokens = self.get_tokens(filename_base)
        final_content = self.template_content.replace("{tokens}", tokens)

        # todo последний файл response.txt из out/agentkotru_bot
        # todo получить все значения

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(final_content)
        print(f"Обновлён: {html_path} (токены: {tokens})")

    def run(self):
        if not self.out_dir.exists():
            print(f"Ошибка: каталог '{self.out_dir}' не существует", file=sys.stderr)
            sys.exit(1)

        jsonl_files = list(self.out_dir.glob("*.jsonl"))
        if not jsonl_files:
            print("Нет файлов .jsonl в каталоге 'out'")
            return

        for jsonl_file in jsonl_files:
            self.process_file(jsonl_file)


if __name__ == "__main__":
    processor = LLMDocumentProcessor()
    processor.run()