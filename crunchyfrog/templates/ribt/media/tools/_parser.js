/**
* Parse the DOM for occurences of ribtType
*/
dojo.provide('RibtTools.Mvc.Parser');

dojo.require('RibtTools.Error');

dojo.declare('RibtTools.Mvc.Parser', null, {
    // Constant defines to support IE
    DOCUMENT_FRAGMENT_NODE: document.DOCUMENT_FRAGMENT_NODE || 11,

    ELEMENT_NODE: document.ELEMENT_NODE || 1,

    // Contructor
    constructor: function() {
        this.instanceClasses = {};
    },

    /**
     * Looks through a DOMNode and finds ribtType attributes
     */
    parse: function(node) {
        node = node || dojo.body();

        if (node.nodeType == this.DOCUMENT_FRAGMENT_NODE) {
            var tempArray = [];

            for (var i; i < node.childNodes.length; i++)
                tempArray.push(node.childNodes.item(i));

            node = tempArray;
        }

        node = (node.length) ? node : [node];

        dojo.forEach(node, function(element) {
            if (element.nodeType != this.ELEMENT_NODE) { return; }

            dojo.query('*[ribtType]', element).forEach(this._createController, this);

            // Let's check the element itself, maybe it has an ribtType
            elementType = dojo.attr(element, 'ribtType');
            if (elementType) {
                this._createController(element);
            }
        }, this);
    },

    /**
     * Places content within a refNode according to position
     *
     * If there are ribtType attributes within, it will parse those and act
     * accordingly.
     */
    place: function(node, refNode, position) {
        if(dojo.isString(node)){
            node = dojo.trim(node);
            node = node.charAt(0) == "<" ? dojo._toDom(node, refNode.ownerDocument) : dojo.byId(node);
        }

        // Remove references to the controller so gc can happen
        position = position.toLowerCase();
        if (position == 'replace' || position == 'only') {
            dojo.query('*[ribtType]', refNode).forEach(function(element) {
                if (element._controller) {
                    element._controller.destroy();
                    delete element._controller;
                }
            })

            // Do we have one on the refNode itself
            if (position == 'replace' && refNode._controller) {
                refNode._controller.destroy();
                delete refNode._controller;
            }
        }

        var toParse = node;

        if (node.nodeType == this.DOCUMENT_FRAGMENT_NODE) {
            toParse = [];

            for (var i=0; i < node.childNodes.length; i++)
                toParse.push(node.childNodes.item(i));
        }

        dojo.place(node, refNode, position);
        this.parse(toParse);
    },

    /**
     * Takes a given element containing an ribtType attribute and creates the
     * controller specified by that value
     */
    _createController: function(element) {
        var ribtType = dojo.attr(element, 'ribtType');
        // Create our object and give it the element
        try {
            var clsInfo = this.getClassInfo(ribtType);
            var obj = new clsInfo['cls'](element, clsInfo['params']);
            // Hang the new obj off the element, during garbage collection we
            // can be intelligent about how we destroy the view and controller
            element._controller = obj;
        } catch (e) {
            throw new RibtTools.Error('Unable to create an instance of ' + ribtType + ', error was: ' + e.message);
        }
    },

    /**
     * Stolen from Dojo
     */
    val2type: function(value) {
        if (dojo.isString(value)){ return "string"; }
        if (typeof value == "number"){ return "number"; }
        if (typeof value == "boolean"){ return "boolean"; }
        if (dojo.isFunction(value)){ return "function"; }
        if (dojo.isArray(value)){ return "array"; } // typeof [] == "object"
        if (value instanceof Date) { return "date"; } // assume timestamp
        if (value instanceof dojo._Url){ return "url"; }
        return "object";
    },

    /**
     * Stolen from Dojo
     */
    str2obj: function(value,  type) {
        switch(type){
            case "string":
                return value;
            case "number":
                return value.length ? Number(value) : NaN;
            case "boolean":
                // for checked/disabled value might be "" or "checked".  interpret as true.
                return typeof value == "boolean" ? value : !(value.toLowerCase()=="false");
            case "function":
                if(dojo.isFunction(value)){
                    value=value.toString();
                    value=dojo.trim(value.substring(value.indexOf('{')+1, value.length-1));
                }
                try{
                    if(value.search(/[^\w\.]+/i) != -1){
                        // TODO: "this" here won't work
                        value = nameAnonFunc(new Function(value), this);
                    }
                    return dojo.getObject(value, false);
                }catch(e){ return new Function(); }
            case "array":
                return value ? value.split(/\s*,\s*/) : [];
            case "date":
                switch(value){
                    case "": return new Date("");    // the NaN of dates
                    case "now": return new Date();    // current date
                    default: return dojo.date.stamp.fromISOString(value);
                }
            case "url":
                return dojo.baseUrl + value;
            default:
                return dojo.fromJson(value);
        }
    },

    /**
     * Taken mostly from Dojo's builtin getClassInfo method
     */
    getClassInfo: function(className){
        if(!this.instanceClasses[className]){
            // get pointer to widget class
            var cls = dojo.getObject(className);
            if(!dojo.isFunction(cls)){
                throw new RibtTools.Error("Could not load class '" + className +
                    "'. Did you spell the name correctly and use a full path, like 'dijit.form.Button'?");
            }
            var proto = cls.prototype;

            // get table of parameter names & types
            var params = {};
            for(var name in proto){
                var defVal = proto[name];
                if (dojo.isFunction(defVal)) { continue; }
                if(name.charAt(0)=="_"){ continue; }     // skip internal properties
                params[name]=this.val2type(defVal);
            }

            this.instanceClasses[className] = { cls: cls, params: params };
        }
        return this.instanceClasses[className];
    }
});