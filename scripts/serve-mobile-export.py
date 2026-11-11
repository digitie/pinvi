"""N150 격리 QA에서 Expo의 extensionless 정적 경로를 제공한다."""
from argparse import ArgumentParser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class ExpoExportHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        candidate = super().translate_path(path)
        if not Path(candidate).exists():
            html = candidate.rstrip("/") + ".html"
            if Path(html).is_file():
                return html
        return candidate


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--directory", required=True)
    options = parser.parse_args()
    handler = partial(ExpoExportHandler, directory=options.directory)
    ThreadingHTTPServer(("127.0.0.1", 12805), handler).serve_forever()
