odoo.define('export_on_filter.DataExport', function (require) {
"use strict";
console.log("NEW JS FILE")
var DataExport = require('web.DataExport');
var core = require('web.core');
var crash_manager = require('web.crash_manager');
var data = require('web.data');
var Dialog = require('web.Dialog');
var framework = require('web.framework');
var pyeval = require('web.pyeval');

var QWeb = core.qweb;
var _t = core._t;

DataExport.include({
	start: function() {
        var self = this;
        var waitFor = [this._super.apply(this, arguments)];

        this.$fields_list = this.$('.o_fields_list');
        this.$import_compat_radios = this.$('.o_import_compat input');

        waitFor.push(this.rpc('/web/export/formats', {}).then(do_setup_export_formats));

        var got_fields = new $.Deferred();
        this.$import_compat_radios.change(function(e) {
            self.$('.o_field_tree_structure').remove();

            self.rpc("/web/export/get_fields", {
                model: self.dataset.model,
                import_compat: !!$(e.target).val(),
            }).done(function (records) {
                var compatible_fields = _.map(records, function (record) {return record.id});
                self.$fields_list
                    .find('option')
                    .filter(function () {
                        var option_field = $(this).attr('value');
                        if (compatible_fields.indexOf(option_field) === -1) {
                            return true;
                        }
                    })
                    .remove();
                got_fields.resolve();
                self.on_show_data(records);
            });
        }).eq(0).change();
        waitFor.push(got_fields);

        waitFor.push(this.getParent().get_active_domain().then(function (domain) {
        	console.log("DOMAIN : ", domain)
            if (domain === undefined || domain.length == 0) {
                self.ids_to_export = self.getParent().get_selected_ids();
                self.domain = self.dataset.domain;
            } else {
                self.ids_to_export = false;
                self.domain = domain;
            }
            self.on_show_domain();
        }));

        waitFor.push(this.show_exports_list());

        return $.when.apply($, waitFor);

        function do_setup_export_formats(formats) {
            var $fmts = self.$('.o_export_format');
            
            _.each(formats, function(format, i) {
                var $radio = $('<input/>', {type: 'radio', value: format.tag, name: 'o_export_format_name'});
                var $label = $('<label/>', {html: format.label});

                if (format.error) {
                    $radio.prop('disabled', true);
                    $label.html(_.str.sprintf("%s — %s", format.label, format.error));
                }

                $fmts.append($("<div/>").append($radio, $label));
            });

            self.$export_format_inputs = $fmts.find('input');
            self.$export_format_inputs.first().prop('checked', true);
        }
    },
	
})

})