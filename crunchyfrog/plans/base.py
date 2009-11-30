import copy
import os
import filecmp
import shutil
import yaml
from django.template import Template, TemplateDoesNotExist, loader
from urlparse import urljoin
from crunchyfrog.conf import settings
from crunchyfrog.processor import clevercss

def find_directory_from_loader(page_instructions, asset):
    from django.template.loaders.app_directories import app_template_dirs
    from django.conf import settings
    template_dirs = list(settings.TEMPLATE_DIRS) + list(app_template_dirs)

    for dir in template_dirs:
        asset_dir = os.path.join(dir, asset)
        if os.path.isdir(asset_dir):
            return asset_dir

    raise TemplateDoesNotExist, ('Unable to find a directory within known '
        'template directories: %s' % asset)

def process_clevercss(source):
    """
    This is part of the processing_funcs that Renderer will use to perform any
    special transformations or filtering on the output of a rendered template.

    This particular one uses CleverCSS to process a meta-css file and convert
    it into normal css.  More info at http://sandbox.pocoo.org/clevercss/
    """
    return clevercss.convert(source)

class BasePlan(object):
    """
    Base class that all the plans can subclass.  It provides common things like
    copying directories, and other fancy pants things like that.
    """

    """
    These are a set of special functions that can be used to manipulate the
    source of the page.  The way these get triggered is through the attribute
    "process:" in the yaml file.  Here's a quick example.

        static: myapp/common.css
        process: clevercss

    As the instruction is parsed, we come across process and if it matches a
    defined processing_funcs we will provide the source of the page and allow
    it to be modified by the function.
    """
    processing_funcs = {
        'clevercss': process_clevercss
    }

    cache_prefix = None

    def find_template_source(self, name, dirs=None):
        """
        This is a copy paste job from django.template.loader.

        The reason you find this here is that in DEBUG mode, Django will not
        return the origin, which is imporant to us since we are trying to mirror
        the directory structure and also copy some of the files inside of any media
        directory into the cache as well.

        So, we have to implement our own so that we are always able to determing
        the origin
        """
        # Calculate template_source_loaders the first time the function is executed
        # because putting this logic in the module-level namespace may cause
        # circular import errors. See Django ticket #1292.
        assert loader.template_source_loaders, 'The template loader has not initialized the template_source_loader, this is very unsual'

        for djangoloader in loader.template_source_loaders:
            try:
                source, display_name = djangoloader(name, dirs)
                origin = loader.LoaderOrigin(display_name, djangoloader, name, dirs)
                return (source, origin)
            except TemplateDoesNotExist:
                pass

        raise TemplateDoesNotExist, name

    def __init__(self, context, render_full_page):
        self.cache_root = os.path.join(
            settings.CRUNCHYFROG_CACHE_ROOT, self.cache_prefix)
        self.cache_url = settings.CRUNCHYFROG_CACHE_URL
        self.context = context
        self.render_full_page = render_full_page

        """
        As we process the page instructions, we gather the output we need to
        convert this into an html page inside this dictionary
        """
        self.prepared_instructions = {}
        self.prepared_instructions['render_full_page'] = self.render_full_page

        if not os.path.exists(self.cache_root):
            os.makedirs(self.cache_root)

    def get_media_source(self, template_name, process_func=None, context=None):
        """
        Responsible for taking a template and generating the contents.

            * Renders the template with the given context if applicable
            * Passes it through the process function if provided
        """
        source, origin = self.find_template_source(template_name)

        if context:
            template = Template(source)
            source   = template.render(context)

        if process_func:
            source = process_func(source)

        return source

    def copy_to_media(self, template_name, process_func=None):
        """
        Part of our goal here is to make the placement of media a transparent deal.
        Django does not currently make this easy, you typically have to handle your
        media in a pretty manual fashion.

        This method takes a file that is somewhere in your template path (for
        example /blog/templates/blog/list/media/css/screen.css and copies it
        to the cache.  It ends up having the same directory structure, so in the
        end gets copied to MEDIA_ROOT/cfcache/blog/media/css/screen.css.

        """
        dirpath  = os.path.join(self.cache_root, os.path.dirname(template_name))
        filename = os.path.basename(template_name)
        fullpath = os.path.join(dirpath, filename)

        if settings.DEBUG:
            if not os.path.exists(dirpath):
                os.makedirs(dirpath)

            source, origin = self.find_template_source(template_name)

            source = self.get_media_source(template_name, process_func)

            f = open(fullpath, 'w')
            f.write(source)
            f.close()

        return urljoin(self.cache_url, template_name), filename

    def prepare_file(self, item_name, page_instructions):
        """
        This method takes lines from our YAML files and decides what to do with
        them.

        An example is::

            js:
                - url: http://somesite.com/somefile.html

            css:
                - static: blog/index/

        This method is a factored out version of prepare_css and prepare_js.
        """
        if not self.prepared_instructions.has_key(item_name):
            self.prepared_instructions[item_name] = []

        for instruction in getattr(page_instructions, item_name):
            if instruction.has_key('url'):
                self.prepared_instructions[item_name].append({ 'location': instruction['url'] })
            else:
                template_name = context = process_func = None

                if instruction.has_key('process') and self.processing_funcs.has_key(instruction['process']):
                    process_func = self.processing_funcs[instruction['process']]
                elif instruction.has_key('process'):
                    raise AttributeError('Could not find a process function matching %s, available ones are: %s' % 
                        (instruction['process'], ', '.join(self.processing_funcs.keys()),))

                item = copy.copy(instruction)

                if instruction.has_key('static'):
                    template_name = instruction['static']
                    location, filename = self.copy_to_media(template_name, process_func)
                    item['location'] = location
                elif instruction.has_key('inline'):
                    template_name = instruction['inline']
                    context = self.context
                    source = self.get_media_source(template_name, process_func, context)
                    item['source'] = source

                assert template_name, 'You must provide either "static" or "inline" properties that point to a file, provided object was %r' % instruction

                if instruction.has_key('include') and not instruction['include']:
                    if instruction.has_key('inline'):
                        raise AttributeError('You have specified inline and '
                            'include: false, these really don\'t make sense '
                            'together')
                    continue

                self.prepared_instructions[item_name].append(item)

    def prepare_assets(self, page_instructions, assets=None):
        """
        There are some special cases when working with css and javascript that
        we make allowances for.

        The first is css.  When you author your css it's normal to see
        references to images like this::

            background-image: url(../img/header/background.png)

        CSS authors are used to referencing images this way.  Since we cache css files
        from within the app to the MEDIA_ROOT, we need to also copy images that may be
        used.  We do this by looking for media/img relative to the yaml file that was
        used to generate the page instructions and copy this entire directory to the
        cache.

        The same thing goes for Javascript templates.  They are not a widely used
        item, but we've included them because it's part of what our original goal
        was when developing this app.

        You can put HTML files in media/js/templates and the entire templates directory
        will be copied into the MEDIA_ROOT in the appropriate spot.  This way your
        javascript files can utilize them without having to worry about where they are.

        This method will work with directories that are relative to the YAML
        file or the app's templates directory.  The following will essentially
        copy the same directory to the cache:

            self.prepare_assets(pi, ('media/js',))
            self.prepare_assets(pi, ('blog/list/media/js',))

        """
        assert type(assets) == tuple or type(assets) == list

        for yaml in page_instructions.yaml:
            # yaml = app/page/page.yaml
            source, origin = self.find_template_source(yaml)
            del source # we don't need it

            origin = str(origin)
            # /Users/me/Development/app/templates/app/page/page.yaml

            yaml_basedir = os.path.dirname(yaml)
            # app/page
            template_basedir = origin[:origin.find(yaml)] 
            # /Users/me/Development/app/templates

            for asset in assets:
                # directory = /media/js/templates
                if not yaml_basedir in asset:
                    # The user might be specifying the directory relative to the
                    # yaml file itself, so we'll add it for them if they gave us
                    # something like 'media/js/templates'
                    directory = os.path.join(yaml_basedir, asset)
                else:
                    directory = asset

                sourcedirectory = os.path.join(template_basedir, directory)

                if not os.path.isdir(sourcedirectory):
                    # We're going to try and find it somewhere else, it may not
                    # be relative to the YAML file
                    #
                    # This is quite possible if the yaml file is processing a
                    # "dojo:" attribute.
                    try:
                        sourcedirectory = find_directory_from_loader(page_instructions, asset)
                        # We need to reset this, it has the yaml_basedir on it
                        # at this point
                        directory = asset
                    except TemplateDoesNotExist:
                        continue

                if not os.path.isdir(sourcedirectory): continue

                cachedirectory = os.path.join(self.cache_root, directory)

                if os.path.isdir(cachedirectory):
                    if self.assets_are_stale(sourcedirectory, cachedirectory):
                        shutil.rmtree(cachedirectory)
                    else:
                        continue

                shutil.copytree(sourcedirectory, cachedirectory)

    def assets_are_stale(self, sourcedirectory, cachedirectory):
        """
        Looks through the given directories, determining if they are different
        """
        comparison = filecmp.dircmp(sourcedirectory, cachedirectory, [], [])
        if comparison.left_only or comparison.right_only:
            # We have files in one directory and not the other
            return True
        if comparison.diff_files:
            # Some of the files have changed
            return True

        return False

    def prepare_title(self, page_instructions):
        """
        Prepares the title for the page
        """
        template = Template(str(page_instructions.title))
        self.prepared_instructions['title'] = unicode(template.render(self.context))

    def prepare_body(self, page_instructions):
        """
        Takes the body section and renders it, storing it in prepared_instructions
        """
        template = loader.get_template(str(page_instructions.body))
        self.context['__page_instructions'] = page_instructions
        self.prepared_instructions['body'] = unicode(template.render(self.context))

    def prepare_meta(self, page_instructions):
        """
        Prepares the meta section
        """
        self.prepared_instructions['meta'] = page_instructions.meta

    def prepare_dojo(self, page_instructions):

        dojo = page_instructions.dojo

        self.prepared_instructions['dojo'] = dojo

        for dojo_module in dojo:
            assert 'namespace' in dojo_module, ('You are missing the '
                'namespace attribute for this item')
            assert 'location' in dojo_module, ('You are missing the '
                 'location attribute for this item')
            assert 'require' in dojo_module, ('You are missing the '
                 'require list for this item')

            namespace = dojo_module['namespace']
            location = dojo_module['location']
            require = dojo_module['require']

            """
            We're going to copy all the files that are in this directory to the
            cache.  This is not ideal, as not all the files may be used but the
            alternative is we ask the user specifically which ones they need.
            Since this is within the context of Dojo, that may not make the most
            sense.
            """
            self.prepare_assets(page_instructions, (location,))

    def prepare(self, page_instructions):
        self.page_instructions = page_instructions

        self.prepare_title(page_instructions)
        self.prepare_body(page_instructions)
        self.prepare_js(page_instructions)
        self.prepare_css(page_instructions)
        self.prepare_meta(page_instructions)
        self.prepare_dojo(page_instructions)

        return self.prepared_instructions
