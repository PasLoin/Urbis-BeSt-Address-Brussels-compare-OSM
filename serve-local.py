#!/usr/bin/env python3
from __future__ import annotations

import argparse
import functools
import os
import re
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class RangeRequestHandler(SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler with support for single byte ranges."""

    range_re = re.compile(r"bytes=(\d*)-(\d*)$")

    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()

        ctype = self.guess_type(path)

        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return None

        fs = os.fstat(f.fileno())
        size = fs.st_size

        range_header = self.headers.get("Range")
        if range_header:
            match = self.range_re.fullmatch(range_header.strip())
            if not match:
                f.close()
                self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE, "Invalid Range")
                return None

            start_s, end_s = match.groups()
            if start_s == "" and end_s == "":
                f.close()
                self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE, "Invalid Range")
                return None

            if start_s == "":
                length = int(end_s)
                if length <= 0:
                    f.close()
                    self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE, "Invalid Range")
                    return None
                start = max(0, size - length)
                end = size - 1
            else:
                start = int(start_s)
                end = int(end_s) if end_s else size - 1

            if start >= size or end < start:
                f.close()
                self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE, "Range out of bounds")
                return None

            end = min(end, size - 1)
            content_length = (end - start) + 1

            self.send_response(HTTPStatus.PARTIAL_CONTENT)
            self.send_header("Content-type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(content_length))
            self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
            self.end_headers()
            f.seek(start)
            self.range = (start, end)
            return f

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-type", ctype)
        self.send_header("Content-Length", str(size))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
        self.end_headers()
        self.range = None
        return f

    def copyfile(self, source, outputfile):
        if getattr(self, "range", None) is None:
            return super().copyfile(source, outputfile)

        start, end = self.range
        remaining = (end - start) + 1
        bufsize = 64 * 1024
        while remaining > 0:
            chunk = source.read(min(bufsize, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serveur local avec support des requêtes Range.")
    parser.add_argument("port", nargs="?", type=int, default=8000)
    parser.add_argument("--dir", default=".", help="dossier à servir, par exemple _site")
    args = parser.parse_args()
    handler = functools.partial(RangeRequestHandler, directory=os.path.abspath(args.dir))
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as httpd:
        print(f"Serving {args.dir} with byte-range support on http://127.0.0.1:{args.port}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
