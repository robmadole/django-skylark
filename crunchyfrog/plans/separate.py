from base import BasePlan

class SeparateEverything(BasePlan):
    cache_prefix = 'se'

    def prepare_js(self, page_instructions):
        """
        Processes the js section of the page instructions
        """
        if hasattr(page_instructions, 'js'):
            self.prepare_assets(page_instructions, ('media/js/templates',))

        self.prepare_file('js', page_instructions)

    def prepare_css(self, page_instructions):
        """
        Processes the css section
        """
        if hasattr(page_instructions, 'css'):
            self.prepare_assets(page_instructions, ('media/img',))

        self.prepare_file('css', page_instructions)
