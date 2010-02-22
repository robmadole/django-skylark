dojo.provide('RibtTools.Mvc.Controller');

dojo.require('RibtTools.Error');
dojo.require('RibtTools.Mvc.Events');
dojo.require('RibtTools.Mvc.SubscriptionCache');
dojo.require('RibtTools.Mvc.History');

/**
 * Base Controller
 */
dojo.declare('RibtTools.Mvc.Controller', null, {
    /**
     * Implemented controller must set this.view
     */
    view: null,

    /**
     * Constructor
     */
    constructor: function(domNode, params, injectedData) {
        if ($CF.INSTRUMENTED) {
            dojo.publish(RibtTools.Mvc.Events.New.Controller, [ this ]);
        }

        this._injectedData      = injectedData || undefined;
        this._subscriptionCache = new RibtTools.Mvc.SubscriptionCache;
        this._delegates         = [];

        if (domNode) {
            this._originalDomNode = dojo.clone(domNode);
            this._setDomNode(domNode, params);
        }

        if (injectedData) {
            // We'll do a similar thing we did for the domNode, but the data
            // inside this object overrides everything
            this._params = params;
            for (name in injectedData) {
                this[name] = injectedData[name];
            }
        }
    },

    /**
     * Sets the root node for this controller, and pulls out variables for
     * consumption
     */
    _setDomNode: function(domNode, params) {
        this.domNode = domNode;

        if (!dojo.attr(this.domNode, 'ribtType')) {
            dojo.attr(this.domNode, 'ribtType', this.declaredClass);
        }

        if (dojo.attr(this.domNode, 'ribtBind') || dojo.attr(this.domNode, 'ribtGroup')) {
            throw new RibtTools.Error('You cannot use ribtBind or ribtGroup on the same node as ribtType');
        }

        if (params) {
            this._params = {};
            // Go through the domNode and pull out variables on the root
            for (var name in params) {
                var attr = dojo.attr(this.domNode, name);

                if (attr) {
                    this._params[name] = params[name];
                    this[name] = ribt.str2obj(attr, params[name]);
                }
            }
        }
    },

    /**
     * Used to create another controller that this controller is a parent of
     */
    createDelegate: function(options) {
        var cls = options['class'] || undefined;
        var domNode = options['domNode'] || undefined;
        var injectData = options['injectData'] || true;

        if (cls) {
            var injectedData = {}

            if (injectData) {
                for (var name in this._params) {
                    var val = this[name];
                    injectedData[name] = val;
                }
            }

            var obj = this._createDelegateInstance(cls, domNode, this._params, injectedData);
            obj._parentController = this;
            this._delegates.push(obj);
            return obj;
        }

        return null;
    },

    _createDelegateInstance: function(cls, domNode, params, injectedData) {
        return new cls(domNode, this._params, injectedData);
    },

    /**
     * Removes a delegate from the delegates array
     */
    spliceDelegate: function(delegate) {
        for (var i in this._delegates) {
            if (this._delegates[i] == delegate) {
                return this._delegates.splice(i, 1);
            }
        }

        return null;
    },

    /**
     * Deletes a delegate
     */
    deleteDelegate: function(delegate) {
        this.spliceDelegate(delegate);

        delegate.destroy();

        delete delegate;
    },

    /**
     * Sets up how this controller will handle the back and forward buttons (and
     * bookmarks)
     */
    initHistoryHandler: function(args) {
        if (this._subscriptionCache.contains(this, args.handler)) {
            throw new RibtTools.Error('You are trying to initialize the history handler ' +
                'after a subscription has been made to ' +
                args.handler);
        }
        var travel = args.handler || false;

        RibtTools.Mvc.History.registerTravel(this, travel);
    },

    /**
     * Part of the history management, what do we have to do to get our page
     * back to the initial state it was in upon load without actually reloading
     * the page.
     *
     * Most of the time, this can be accomplished by caching the domNode that is
     * passed into the controller when it starts.  You can then
     * ribt.place(domNodeCache, 'replace') and have everything work out
     * correctly.
     */
    _restoreInitialState: function() {
        this.publish(RibtTools.Mvc.Events.History.RestoreInitialState,
            [ this._originalDomNode || null ]
        );
    },

    /**
     * Subscribe to an event, but tie it to our controller/view pair
     */
    subscribe: function(topic, context, method) {
        this._subscriptionCache.add(context, method);

        var realFunc = dojo.hitch(context, method);
        var wrapperContext = { 'scope': this, 'realFunc': realFunc };

        dojo.subscribe(topic, wrapperContext, function() {
            var args = Array.prototype.slice.call(arguments);
            var view = args[0];

            if (!view.declaredClass) {
                throw new RibtTools.Error('You cannot subscribe using this.subscribe ' +
                    'if the event wasn\'t published with the view\'s this.publish.');
            }

            if (view == this.scope) {
                // The view is not a view, but our controller, it's ok to let
                // this one pass
                // do nothing
            } else if (!this.scope._viewApplies(view)) {
                // This view is not the one we are looking for
                return;
            }
            args.shift();
            this.realFunc.apply(null, args);
        });
    },

    /**
     * Convenience method to publish events from the view to the controller
     *
     * This is going to include the "this"
     */
    publish: function(topic, args) {
        args = args || [];

        args.unshift(this);

        dojo.publish(topic, args);
    },

    /**
     * Whether a view pertains to this controller or not
     *
     * This also checks for any delegates, and returns true if one of the
     * delegates has this view
     */
    _viewApplies: function(view) {
        if (this.view == view) { return true; }

        // This controller is a delegate of another
        if (this._parentController) {
            if (this._parentController.view == view) { return true; }
        }

        // See if this controller has any delegates that this view applies to
        if (this._delegates.length > 0) {
            return this._delegateApplies(view, this._delegates);
        }

        return false;
    },

    /**
     * Tests whether a delegate applies or any delegates on the passed delegate
     *
     * This function recurses so any level of delegation should correctly match
     * further up the tree
     */
    _delegateApplies: function(view, delegates) {
        for (var i in delegates) {
            var delegate = delegates[i];

            if (dojo.isFunction(delegate)) { continue; }

            if (delegate.view == view) { return true; }

            if (delegate._delegates.length > 0) {
                 if (this._delegateApplies(view, delegate._delegates)) { return true; }
            }
        }

        return false;
    },

    /**
     * Do whatever is necessary to remove things, this gets called by ribt.place
     * while we are removing elements in the DOM
     */
    destroy: function() {
        while (this._delegates.length > 0) {
            this.deleteDelegate(this._delegates[0]);
        }

        this.view.destroy();
    }
});
