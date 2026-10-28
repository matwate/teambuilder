$(document).ready(function() {
    // Page navigation handlers
    $('#page-calculator').change(function() {
        if ($(this).is(':checked')) {
            window.location.href = '/';
        }
    });

    $('#page-search').change(function() {
        if ($(this).is(':checked')) {
            window.location.href = '/search';
        }
    });

    $('#page-bulk-ko').change(function() {
        if ($(this).is(':checked')) {
            window.location.href = '/bulk-ko';
        }
    });

    $('#page-bulk-survive').change(function() {
        if ($(this).is(':checked')) {
            // Already on bulk-survive page
        }
    });

    // Initialize Select2 for Pokemon dropdown
    $('#attacker').select2({
        placeholder: 'Select Pokemon',
        allowClear: true,
        width: '100%'
    });

    // Initialize Select2 for move dropdown
    $('#move').select2({
        placeholder: 'Select Move',
        allowClear: true,
        width: '100%'
    });

    // Ability filter: keeps only the defenders that can have the ability.
    // Which of its abilities each one survives with is the calculation's call.
    $('#filter_ability').append('<option value="">Any</option>');
    $.get('/api/abilities', function(data) {
        data.forEach(function(ability) {
            $('#filter_ability').append('<option value="' + ability + '">' + ability + '</option>');
        });
    });
    $('#filter_ability').select2({
        placeholder: 'Any',
        allowClear: true,
        width: '100%'
    });

    // Initialize Select2 for type filter (options already in HTML)
    $('#filter_type1').select2({
        placeholder: 'Any',
        allowClear: true,
        width: '100%'
    });

    // Load Pokemon list
    $.get('/api/pokemon', function(data) {
        data.forEach(function(pokemon) {
            $('#attacker').append('<option value="' + pokemon + '">' + pokemon + '</option>');
        });
    });

    // Load items
    $.get('/api/items', function(data) {
        $('.item').each(function() {
            const $this = $(this);
            $this.empty();
            $this.append('<option value="">Select Item</option>');
            data.forEach(function(item) {
                $this.append('<option value="' + item + '">' + item + '</option>');
            });
            $this.trigger('items-loaded');
            $this.select2({
                placeholder: 'Select Item',
                allowClear: true,
                width: '100%'
            });
        });
    });

    // When attacker is selected, load its moves and abilities
    $('#attacker').change(function() {
        const pokemon = $(this).val();
        $('#move').empty().append('<option value="">Select Move</option>').val('').trigger('change');
        $('#attacker_item').val('').trigger('change');
        $('#attacker_ability').empty().append('<option value="">Any</option>').val('').trigger('change');
        if (pokemon) {
            // Load moves for this specific Pokemon
            $.get('/api/moves/' + pokemon, function(data) {
                $('#move').empty().append('<option value="">Select Move</option>');
                data.forEach(function(move) {
                    $('#move').append('<option value="' + move + '">' + move + '</option>');
                });
            });

            // Load abilities
            $.get('/api/abilities/' + pokemon, function(data) {
                $('#attacker_ability').empty().append('<option value="">Any</option>');
                data.forEach(function(ability) {
                    $('#attacker_ability').append('<option value="' + ability + '">' + ability + '</option>');
                });
                // Initialize Select2 for ability if not already initialized
                if (!$('#attacker_ability').data('select2')) {
                    $('#attacker_ability').select2({
                        placeholder: 'Select Ability',
                        allowClear: true,
                        width: '100%'
                    });
                }
                // Auto-select if only one ability and apply its field effect.
                if (data.length === 1) {
                    $('#attacker_ability').val(data[0]).trigger('change');
                }
            });
        } else {
            $('#move').empty().append('<option value="">Select Move</option>');
        }
    });

    // Search button click handler
    $('#searchBtn').click(function() {
        performBulkSurvive();
    });

    // Cancel button click handler
    $('#cancelBtn').click(function() {
        if (window.eventSource) {
            window.eventSource.close();
            window.eventSource = null;
        }
        finishSearch();
        if (rows.length === 0) {
            $('#resultsBody').html('<tr><td colspan="6" style="text-align: center;">Search cancelled</td></tr>');
        }
    });

    // Every survivor streamed in so far, kept so the table can be sorted at the end.
    let rows = [];
    let fairyAuraActive = false;

    function esc(value) {
        return $('<div>').text(value == null ? '' : value).html();
    }

    // Put the controls back the way they were before a search started.
    function finishSearch() {
        $('#searchBtn').prop('disabled', false);
        $('#cancelBtn').hide();
        $('#progressBar').hide();
        $('#progressText').hide();
    }

    function performBulkSurvive() {
        const attacker = $('#attacker').val();
        const move = $('#move').val();
        if (!attacker || !move) {
            alert('Please select an attacker Pokemon and move');
            return;
        }

            // Collect form data
            const data = {
                attacker: attacker,
                move: move,
                attacker_item: $('#attacker_item').val() || null,
                attacker_ability: $('#attacker_ability').val() || null,
                attacker_evs: $('#attacker_evs').val() || '32',
                defender_item: $('#defender_item').val() || null,
                defender_nature: $('#defender_nature').val() || '1.0',
                percent: $('#survival_percent').val() ? parseFloat($('#survival_percent').val()) : 100.0,
                filter_type1: $('#filter_type1').val() || null,
                filter_ability: $('#filter_ability').val() || null,
                filter_min_bst: $('#filter_min_bst').val() ? parseInt($('#filter_min_bst').val()) : null,
                filter_min_hp: $('#filter_min_hp').val() ? parseInt($('#filter_min_hp').val()) : null,
                format: $('input[name="format"]:checked').val() || 'doubles',
                terrain: $('input[name="terrain"]:checked').val() || null,
                weather: $('input[name="weather"]:checked').val() || null,
                field: $('input[name="fieldState"]:checked').map(function() { return this.value; }).get(),
                spikes: $('input[name="spikes"]:checked').val() || '0',
                isSR: $('#SR').is(':checked'),
                isReflect: $('#reflect').is(':checked'),
                isLightScreen: $('#lightScreen').is(':checked'),
                isAuroraVeil: $('#auroraVeil').is(':checked'),
                isFriendGuard: $('#friendGuard').is(':checked'),
                isProtect: $('#protect').is(':checked'),
                isLeechSeed: $('#leechSeed').is(':checked'),
                isSaltCure: $('#saltCure').is(':checked'),
                isCharge: $('#charge').is(':checked'),
                isHelpingHand: $('#helpingHand').is(':checked'),
                isPowerTrickLeft: $('#powerTrickL').is(':checked'),
                isPowerTrickRight: $('#powerTrickR').is(':checked')
            };
        fairyAuraActive = data.field.includes('FairyAura');

        // Show loading state
        rows = [];
        $('#searchBtn').prop('disabled', true);
        $('#cancelBtn').show();
        $('#progressBar').show();
        $('#progressFill').css('width', '0%');
        $('#progressText').show().text('Initializing...');
        $('#resultsBody').empty();
        $('#resultsCount').text('0 results');

        // Use Server-Sent Events for real-time progress
        const queryString = $.param(data);
        window.eventSource = new EventSource('/api/bulk-survive-stream?' + queryString);

        window.eventSource.onmessage = function(event) {
            const msg = JSON.parse(event.data);

            if (msg.type === 'start') {
                $('#progressText').text(`Starting to check ${msg.total} Pokemon...`);
            } else if (msg.type === 'progress') {
                const percent = msg.percent;
                $('#progressFill').css('width', percent + '%');
                $('#progressText').text(`Checking ${msg.current}/${msg.total}: ${msg.name}... (${percent}%)`);
            } else if (msg.type === 'result') {
                // Append result to table in real-time
                appendResult(msg.result);
            } else if (msg.type === 'complete') {
                window.eventSource.close();
                window.eventSource = null;
                $('#progressFill').css('width', '100%');
                $('#searchBtn').prop('disabled', false);
                $('#cancelBtn').hide();

                if (!msg.success) {
                    if (rows.length === 0) {
                        $('#resultsBody').html('<tr><td colspan="6" style="text-align: center; color: red;">Error: ' + esc(msg.error) + '</td></tr>');
                        $('#resultsCount').text('');
                    } else {
                        $('#resultsCount').text(rows.length + ' result' + (rows.length !== 1 ? 's' : '') + ' (stopped early - Error: ' + msg.error + ')');
                    }
                } else {
                    // Rows arrive in roster order; sort them cheapest first now that all are in
                    // (this also shows the "none found" message when nothing survived).
                    displayResults(rows);
                }

                setTimeout(function() {
                    $('#progressBar').hide();
                    $('#progressText').hide();
                }, 1000);
            }
        };

        window.eventSource.onerror = function() {
            if (!window.eventSource) {
                return;  // already closed by 'complete' or Cancel
            }
            window.eventSource.close();
            window.eventSource = null;
            finishSearch();
            $('#resultsBody').html('<tr><td colspan="6" style="text-align: center; color: red;">Connection error</td></tr>');
        };
    }

    function rowHtml(result) {
        const ability = result.ability || 'Any';
        return `
            <tr>
                <td>${esc(result.name)}</td>
                <td>${result.points}</td>
                <td>${result.hp_invest}</td>
                <td>${result.defender_invest}</td>
                <td class="${ability === 'Any' ? 'ability-not-required' : ''}">${esc(ability)}</td>
                <td>${window.bulkResultDescription(result.desc, fairyAuraActive)}</td>
            </tr>
        `;
    }

    function appendResult(result) {
        rows.push(result);
        $('#resultsCount').text(rows.length + ' result' + (rows.length !== 1 ? 's' : ''));
        $('#resultsBody').append(rowHtml(result));
    }

    function displayResults(results) {
        if (results.length === 0) {
            $('#resultsBody').html('<tr><td colspan="6" style="text-align: center;">No defenders found that can survive this attack</td></tr>');
            $('#resultsCount').text('0 results');
            return;
        }

        $('#resultsCount').text(results.length + ' result' + (results.length !== 1 ? 's' : ''));

        // Sort by points (ascending)
        results.sort(function(a, b) {
            return a.points - b.points;
        });

        $('#resultsBody').html(results.map(rowHtml).join(''));
    }
});
