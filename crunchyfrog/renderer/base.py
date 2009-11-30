import copy
import os
import yaml
from django.template import Template, loader
from crunchyfrog import plans
from crunchyfrog.conf import settings

def add_yaml(yamlfile):
    """
    Template tag that can be used to add crunchy dependencies out side the normal PageAssembly
    """
    def render_yaml(yamlfile, page_instructions, context):
        source, origin = loader.find_template_source(yamlfile)
        sourcerendered = Template(source).render(context)

        instructions = yaml.load(sourcerendered)

        page_instructions.add(instructions, yamlfile)

    def process_yaml(func):
        def wrapper(*args, **kwargs):
            context = args[1]

            if context.has_key('__page_instructions'):
                page_instructions = context['__page_instructions']
                render_yaml(yamlfile, page_instructions, context)

            return func(*args, **kwargs)
        return wrapper

    return process_yaml

class Renderer(object):
    """
    The base class that performs the heavy lifting of taking page instructions
    and rendering them into actual HTML.  This class is not meant to be used by
    itself but instead extended.  The template_str class variables should
    contain the template that you wish to use to render whatever kind of page
    you need.  In other words, check out Xhtml401Transitional for an example.
    """
    template_str = None # This is the one that needs to be replaced in the sub class

    """
    Used to place a doctype at the beginning of a rendered page.  This only
    applies to html and xhtml pages that are rendered with a PageAssembly.
    """
    doctype = '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" "http://www.w3.org/TR/html4/loose.dtd">'

    """
    What template do we use to render?
    """
    template_name = 'crunchyfrog/html401.html'
    snippet_template_name = 'crunchyfrog/htmlsnippet.html'

    def __init__(self, page_instructions, context, render_full_page=True):
        self.page_instructions = page_instructions
        self.context           = context
        self.render_full_page  = render_full_page

        t = self.template_name if render_full_page else self.snippet_template_name
        self.template = loader.get_template(t)

    def render(self):
        """
        Takes a chunk of page instructions and renders a page according to the rules
        found within

        This return a string representing the HTML or similar output
        """
        assert self.page_instructions.body, 'The body has not been specified in the page instructions (body: in your yaml file)'

        if self.render_full_page:
            assert self.page_instructions.title, 'The title has not been specified in the page instructions (title: in your yaml file)'

        plan = plans.get_for_context(self.context,
            self.page_instructions.render_full_page)
        prepared_instructions = plan.prepare(self.page_instructions)

        render_context = copy.copy(self.context)
        render_context['cache_url'] = settings.CRUNCHYFROG_CACHE_URL
        render_context['doctype'] = self.doctype
        render_context['prepared_instructions'] = prepared_instructions

        return self.template.render(render_context)
