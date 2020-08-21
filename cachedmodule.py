class CachedModule():
    def __init__(self, path, text_input):
        self.path = path
        self.text_input = text_input
        self.parser = None
        self.decl_parser = None

    def get_text(self):
        return self.text_input

    def parse(self):
        from lexer import Lexer
        from sparser import Parser


cachedmods = {}
