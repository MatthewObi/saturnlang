class CachedModule:
    def __init__(self, path, text_input):
        self.path = path
        self.text_input = text_input
        self.parser = None
        self.decl_parser = None
        self.ast = None

    def add_parsed_ast(self, parsed_ast):
        self.ast = parsed_ast

    def get_parsed_ast(self):
        return self.ast

    def get_text(self):
        return self.text_input
