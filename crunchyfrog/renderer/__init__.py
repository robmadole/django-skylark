from crunchyfrog.renderer.base import add_yaml, Renderer
from crunchyfrog.renderer.html import *
from crunchyfrog.renderer.xhtml import *

renderers = {
    'HTML 4.01 Transitional': Html401Transitional,
    'HTML 4.01 Strict':       Html401Strict,
    'HTML 4.01 Frameset':     Html401Frameset,
    'XHTML 1.0 Transitional': Xhtml1Transitional,
    'XHTML 1.0 Strict':       Xhtml1Strict,
    'XHTML 1.0 Frameset':     Xhtml1Frameset,
}
    
def get(doctype, instructions, context):
    return renderers[doctype](instructions, context)
