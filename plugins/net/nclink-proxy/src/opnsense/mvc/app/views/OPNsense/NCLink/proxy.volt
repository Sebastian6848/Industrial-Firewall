<script>
    $( document ).ready(function() {
        let data_get_map = {'frm_settings':"/api/nclink/settings/get"};
        mapDataToFormUI(data_get_map).done(function(){
            $('.selectpicker').selectpicker('refresh');
            updateServiceControlUI('nclink');
        });

        $("#grid-log").UIBootgrid({
            search:'/api/nclink/log/search',
            options: {
                sorting: false,
                rowSelect: false,
                selection: false,
                rowCount: [50, 100, 200, 500, 1000, 5000],
                formatters: {
                    message: function(column, row) {
                        return $("<div/>").text(row.message || '').html();
                    },
                    details: function(column, row) {
                        return $("<div/>").text(row.details || '').html();
                    }
                }
            },
            tabulatorOptions: {
                index: "rnum"
            }
        });

        $("#refreshLogAct").click(function(event){
            event.preventDefault();
            $('#grid-log').bootgrid('reload');
        });

        $("#reconfigureAct").SimpleActionButton({
            onPreAction: function() {
                const dfObj = new $.Deferred();
                saveFormToEndpoint("/api/nclink/settings/set", 'frm_settings', function(){
                    dfObj.resolve();
                });
                return dfObj;
            }
        });
    });
</script>

<ul class="nav nav-tabs" data-tabs="tabs" id="maintabs">
    <li class="active"><a data-toggle="tab" href="#settings">{{ lang._('Settings') }}</a></li>
    <li><a data-toggle="tab" href="#log">{{ lang._('Log') }}</a></li>
</ul>
<div class="tab-content content-box">
    <div id="settings" class="tab-pane fade in active">
        {{ partial("layout_partials/base_form",['fields':generalForm,'id':'frm_settings'])}}
    </div>
    <div id="log" class="tab-pane fade in">
        <div class="content-box-main">
            <div class="table-responsive">
                <div class="col-sm-12">
                    <div class="btn-group" style="margin-bottom: 10px;">
                        <button id="refreshLogAct" class="btn btn-default" data-toggle="tooltip" type="button" data-original-title="{{ lang._('Refresh') }}">
                            <span class="fa fa-fw fa-refresh"></span>
                        </button>
                    </div>
                    <table id="grid-log" class="table table-condensed table-hover table-striped table-responsive">
                        <thead>
                        <tr>
                            <th data-column-id="timestamp" data-width="150" data-type="string">{{ lang._('Date') }}</th>
                            <th data-column-id="level" data-width="90" data-type="string">{{ lang._('Level') }}</th>
                            <th data-column-id="event" data-width="110" data-type="string">{{ lang._('Event') }}</th>
                            <th data-column-id="direction" data-width="130" data-type="string">{{ lang._('Direction') }}</th>
                            <th data-column-id="peer" data-width="150" data-type="string">{{ lang._('Peer') }}</th>
                            <th data-column-id="message" data-type="string" data-formatter="message">{{ lang._('Message') }}</th>
                            <th data-column-id="details" data-type="string" data-formatter="details" data-visible="false">{{ lang._('Details') }}</th>
                            <th data-column-id="rnum" data-type="numeric" data-visible="false" data-identifier="true"></th>
                        </tr>
                        </thead>
                        <tbody>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
</div>

{{ partial('layout_partials/base_apply_button', {'data_endpoint': '/api/nclink/service/reconfigure', 'data_service_widget': 'nclink'}) }}
