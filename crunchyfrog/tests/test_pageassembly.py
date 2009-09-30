import py.test
import os
import shutil
import re

from nose.tools import with_setup
from nose.result import log
from nose.plugins.attrib import attr
from nose.plugins.skip import SkipTest
from crunchyfrog.page import PageAssembly, RequestContext
from crunchyfrog.page import settings as page_settings
from django.core.exceptions import SuspiciousOperation
from django.http import HttpRequest, HttpResponse, HttpResponseNotFound
from django.template import TemplateDoesNotExist
from django.template import Context, loader
from django.core.management import setup_environ
from django.test.client import Client
from yaml.parser import ParserError
from crunchyfrog import media_cache

try:
    import settings # Assumed to be in the same directory.
except ImportError:
    import sys
    sys.stderr.write("Error: Can't find the file 'settings.py' in the directory containing %r. It appears you've customized things.\nYou'll have to run django-admin.py, passing it your settings module.\n(If the file settings.py does indeed exist, it's causing an ImportError somehow.)\n" % __file__)
    sys.exit(1)

setup_environ(settings)
    
cachedir = os.path.join(os.path.dirname(__file__), 'media/cfcache')

def get_one_file_in(path):
    for file in os.walk(path):
        files = file[2] # the third element is an array of files
        if files:
            return os.path.join(file[0], files[0])

    raise Exception, 'Could not find a file in %s' % path

def get_contents(filename):
    f = open(filename, 'r')

    content = f.read()
    f.close()

    return content

def get_request_fixture():
    request = HttpRequest()
    request.path = '/'
    request.META = { 'REMOTE_ADDR': '127.0.0.1', 'SERVER_NAME': '127.0.0.1', 'SERVER_PORT': '8000' }
    return request

def setup():
    pass

def teardown():
    if os.path.isdir(cachedir):
        shutil.rmtree(cachedir)

"""
To run only one tests you can do something like this.  Edit the setup.cfg file::

    [nosetests]
    attr=focus

This tells nose to only run the tests that have the attribute of "focus".

Your test can look something like this:

    from nose.plugins.attrib import attr
    @attr('focus')
    def test_big_download():
            import urllib
            # commence slowness...

"""

def test_can_not_create_page_assembly():
    py.test.raises(TypeError, "pa = PageAssembly()")
    py.test.raises(TypeError, 'pa = PageAssembly("somefile/test.yaml")')

    """ Make sure that the context is correct """
    c = []
    py.test.raises(AssertionError, 'pa = PageAssembly("somefile/test.yaml", c)')

    """ Make sure that you can't send it an empty yaml file """
    request = get_request_fixture()
    c = RequestContext(request, { 'foo': 'bar' })
    py.test.raises(AssertionError, 'pa = PageAssembly((), c)')

def test_can_create_page_assembly():
    request = get_request_fixture()
    c = RequestContext(request, { 'foo': 'bar' })
    pa = PageAssembly('somefile/that/doesnt/exist.yaml', c)

    assert isinstance(pa, PageAssembly)

    """ We should be able to pass it a tuple with more than one file in it """
    pa = PageAssembly(('somefile/that/doesnt/exist.yaml', 'someother/file.yaml'), c)

def test_missing_template():
    request = get_request_fixture()
    c = RequestContext(request, { 'foo': 'bar' })
    pa = PageAssembly('somefile/that/doesnt/exist.yaml', c)

    py.test.raises(TemplateDoesNotExist, "pa.get_http_response()")

@with_setup(setup, teardown)
def test_returns_http_response():
    request = get_request_fixture()
    c = RequestContext(request, { 'foo': 'bar' })
    pa = PageAssembly('dummyapp/page/sample.yaml', c)

    assert isinstance(pa.get_http_response(), HttpResponse)

def test_provides_page_instructions():
    request = get_request_fixture()
    c = RequestContext(request, { 'foo': 'bar' })
    pa = PageAssembly('dummyapp/page/invalid.yaml', c)

    py.test.raises(ParserError, "pa.get_http_response()")

def test_missing_crunchyfrog_settings():
    from crunchyfrog.conf import settings

    assert settings.MEDIA_URL
    assert settings.MEDIA_ROOT
    assert settings.CRUNCHYFROG_CACHE_ROOT
    assert settings.CRUNCHYFROG_CACHE_URL

@with_setup(setup, teardown)
def test_creates_a_file_in_cache():
    request = get_request_fixture()
    c = RequestContext(request, { 'foo': 'bar' })
    pa = PageAssembly('dummyapp/page/sample.yaml', c)

    assert not os.path.isdir(cachedir)

    pa.dumps()

    assert get_one_file_in(cachedir)

@with_setup(setup, teardown)
def test_creates_a_file_in_cache_with_key():
    request = get_request_fixture()
    c = RequestContext(request, { 'foo': 'bar' })
    pa = PageAssembly('dummyapp/page/sample.yaml', c, 'somekeyname')

    assert not os.path.isdir(cachedir)

    pa.dumps()

    assert get_one_file_in(cachedir)

@with_setup(setup, teardown)
def test_can_render_an_asset():
    client  = Client()
    request = get_request_fixture()

    expected_gray = "body { background-color: gray }\n"
    template_name = 'dummyapp/page/media/css/renderasset.css'
    token_pattern = re.compile('/cfmedia/(?P<token>[0-9]+)/')

    c = RequestContext(request, { 'color': 'gray' })
    pa = PageAssembly('dummyapp/page/renderasset.yaml', c)
    content = pa.dumps()

    # Grab the token out of the content
    token = token_pattern.search(content).groupdict()['token']

    assert media_cache.get(token, template_name) == expected_gray 
    assert client.get('/cfmedia/%s/%s' % (token, template_name,)).content == expected_gray

    # This is a new context object, the token generated from it should be different
    c = RequestContext(request, { 'color': 'gray' })
    pa = PageAssembly('dummyapp/page/renderasset.yaml', c)
    content = pa.dumps()

    old_token = token
    token = token_pattern.search(content).groupdict()['token']

    assert token != old_token

    assert media_cache.get(token, template_name) == expected_gray

    # Change the context and re-render
    c['color'] = 'blue'
    pa = PageAssembly('dummyapp/page/renderasset.yaml', c)
    content = pa.dumps()

    assert media_cache.get(token, template_name) == expected_gray.replace('gray', 'blue')

    assert isinstance(client.get('/cfmedia/0000/not/here'), HttpResponseNotFound)

@with_setup(setup, teardown)
def test_can_render_clevercss():
    request = get_request_fixture()
    c = RequestContext(request, { 'foo': 'bar' })
    pa = PageAssembly('dummyapp/page/clevercss.yaml', c)

    pa.dumps()

    css = get_contents(get_one_file_in(cachedir))

    assert css == 'body {\n  background-color: gray;\n}'

@with_setup(setup, teardown)
def test_missing_yaml_attributes():
    request = get_request_fixture()
    c = RequestContext(request, { 'foo': 'bar' })
    pa = PageAssembly('dummyapp/page/missingbody.yaml', c)

    py.test.raises(AssertionError, "pa.get_http_response()")

    request = get_request_fixture()
    c = RequestContext(request, { 'foo': 'bar' })
    pa = PageAssembly('dummyapp/page/missingtitle.yaml', c)

    py.test.raises(AssertionError, "pa.get_http_response()")

    # Combining them should fix our issue
    request = get_request_fixture()
    c = RequestContext(request, { 'foo': 'bar' })
    pa = PageAssembly(('dummyapp/page/missingbody.yaml', 'dummyapp/page/missingtitle.yaml'), c)

    content = pa.dumps()

    assert isinstance(content, unicode), 'The returned value from dumps() did not return a unicode instance, instead the value was %r' % content 

@with_setup(setup, teardown)
def test_will_not_duplicate_assets():
    request = get_request_fixture()
    c = RequestContext(request, { 'foo': 'bar' })
    pa = PageAssembly('dummyapp/page/duplicateassets.yaml', c)

    content = pa.dumps()

    assert len(re.findall('sample.js', content)) == 1
    assert len(re.findall('files.js', content)) == 1

@with_setup(setup, teardown)
def test_title_tag_is_escaped():
    request = get_request_fixture()
    c = RequestContext(request, { 'title': unicode('Title < > \' "') })
    pa = PageAssembly('dummyapp/page/escapetitle.yaml', c)

    content = pa.dumps()

    assert content.index('Title &lt; &gt; &#39; &quot;')

@with_setup(setup, teardown)
def test_will_copy_assets():
    request = get_request_fixture()
    c = RequestContext(request, { 'title': unicode('Title < > \' "') })
    pa = PageAssembly('dummyapp/page/sample.yaml', c)

    filenames = ('dummyapp/page/media/img/test.png',
                 'dummyapp/page/media/img/notreferenced.png',
                 'dummyapp/page/media/js/templates/sample.js',
                 'dummyapp/page/media/js/notreferenced.js',
                 'dummyapp/page/media/js/templates/notreferenced.html',
                )

    content = pa.dumps()

    assert content.find('notreferenced') == -1, 'Found a reference to a file that has been set include: false in the yaml file.  It should not show up in the rendered output'

    for template_name in filenames:
        assert os.path.isfile(os.path.join(cachedir, template_name))

@with_setup(setup, teardown)
def test_uses_the_page_instructions_cache_if_enabled():
    page_settings.CACHE_BACKEND = 'dummy://'
    page_settings.DEBUG = False

    request = get_request_fixture()
    c = RequestContext(request, { 'foo': 'bar' })
    pa = PageAssembly('dummyapp/page/sample.yaml', c, 'somecachekey')

    pa.dumps()

    assert True

@with_setup(setup, teardown)
def test_references_other_yaml_files():
    request = get_request_fixture()
    c = RequestContext(request, { 'foo': 'bar' })
    pa = PageAssembly('dummyapp/page/uses.yaml', c)

    content = pa.dumps()

    assert len(re.findall('.*\.css', content)) == 3, 'There should be 3 css files from the sample.yaml in here'
    assert content.find('sample.js') < content.find('sampleafter.js'), 'The sample.js should come before the sampleafter.js'

@with_setup(setup, teardown)
def test_renders_meta_section():
    request = get_request_fixture()
    c = RequestContext(request, { 'foo': 'bar' })
    pa = PageAssembly('dummyapp/page/meta.yaml', c, 'metacachekey')

    content = pa.dumps()

    assert content.find('<meta http-equiv="test" content="test-content">') >= 0, 'Could not locate the meta information expected'

@with_setup(setup, teardown)
def test_will_do_conditional_comments():
    request = get_request_fixture()
    c = RequestContext(request, { 'foo': 'bar' })
    pa = PageAssembly('dummyapp/page/ieversion.yaml', c, 'ieversioncachekey')

    content = pa.dumps()

    assert content.find('<!--[if ') >= 0, 'Could not locate the conditional comment for IE we expected'

@with_setup(setup, teardown)
def test_will_use_correct_doctype():
    request = get_request_fixture()
    c = RequestContext(request, { 'foo': 'bar' })
    pa = PageAssembly('dummyapp/page/sample.yaml', c, 'defaultdoctype')

    content = pa.dumps()

    assert content.find('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" "http://www.w3.org/TR/html4/loose.dtd">') >= 0, 'Could not locate the default HTML 4.01 Transitional doctype'

    pa = PageAssembly('dummyapp/page/xhtmlstrict.yaml', c, 'xhtmlstrictdoctype')

    content = pa.dumps()

    assert content.find('<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">') >= 0, 'Could not locate the XHTML 1.0 Strict doctype'

@with_setup(setup, teardown)
def test_add_yaml_decorator():
    request = get_request_fixture()
    c = RequestContext(request, {})
    pa = PageAssembly('dummyapp/tag/tag.yaml', c, 'templatetagcachekey')

    content = pa.dumps()

    assert content.find('<div class="test">This is my tag test</div>') >= 0, 'Template tag did not render its contents'
    assert content.find('/media/cfcache/dummyapp/tag/media/css/screen.css" media="screen">') >= 0, 'Template tag style sheet was not included'
