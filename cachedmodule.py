class CachedModule():
    def __init__(self, path, text_input):
        self.path = path
        self.text_input = text_input

    def get_text(self):
        return self.text_input


cachedmods = {}
