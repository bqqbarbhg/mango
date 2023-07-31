#!/usr/bin/env python3
from http.server import HTTPServer, SimpleHTTPRequestHandler, test
import sys

class CORSRequestHandler (SimpleHTTPRequestHandler):
    def end_headers (self):
        self.send_header('Access-Control-Allow-Origin', '*')
        SimpleHTTPRequestHandler.end_headers(self)

def run(port):
    server_address = ('0.0.0.0', port)
    httpd = HTTPServer(server_address, CORSRequestHandler)
    httpd.serve_forever()

if __name__ == '__main__':
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 8000)
