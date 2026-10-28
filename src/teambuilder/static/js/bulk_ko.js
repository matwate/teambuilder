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
            // Already on bulk-ko page
        }
    });

    $('#page-bulk-survive').change(function() {
        if ($(this).is(':checked')) {
            window.location.href = '/bulk-survive';
        }
    });

    // Initialize Select2 for Pokemon dropdown
    $('#defender').select2({
        placeholder: 'Select Pokemon',
        allowClear: true,
        width: '100%'
    });

    // Initialize Select2 for move input
    $('#move').select2({
        placeholder: 'Any (best move)',
        allowClear: true,
        width: '14em'
    });

    // Initialize Select2 for type filter (options already in HTML)
    $('#filter_type1').select2({
        placeholder: 'Any',
        allowClear: true,
        width: '14em'
    });

    let fairyAuraActive = false;

    // Load Pokemon list
    $.get('/api/pokemon', function(data) {
        data.forEach(function(pokemon) {
            $('#defender').append('<option value="' + pokemon + '">' + pokemon + '</option>');
        });
    });

    // Load all moves
    $.get('/api/moves', function(data) {
        $('#move').append('<option value="">Any (best move)</option>');
        data.forEach(function(move) {
            $('#move').append('<option value="' + move + '">' + move + '</option>');
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
                width: '14em'
            });
        });
    });

    // When defender is selected, load its abilities
    $('#defender').change(function() {
        const pokemon = $(this).val();
        $('#move').val('').trigger('change');
        $('#defender_item').val('').trigger('change');
        $('#defender_ability').empty().append('<option value="">Any</option>').val('').trigger('change');
        if (pokemon) {
            $.get('/api/abilities/' + pokemon, function(data) {
                $('#defender_ability').empty().append('<option value="">Any</option>');
                data.forEach(function(ability) {
                    $('#defender_ability').append('<option value="' + ability + '">' + ability + '</option>');
                });
                // Initialize Select2 for ability if not already initialized
                if (!$('#defender_ability').data('select2')) {
                    $('#defender_ability').select2({
                        placeholder: 'Select Ability',
                        allowClear: true,
                        width: '14em'
                    });
                }
                // Auto-select if only one ability
                if (data.length === 1) {
                    $('#defender_ability').val(data[0]).trigger('change');
                }
            });
        }
    });

    // Search button click handler
    $('#searchBtn').click(function() {
        performBulkKO();
    });

    // Cancel button click handler
    $('#cancelBtn').click(function() {
        if (window.eventSource) {
            window.eventSource.close();
            window.eventSource = null;
        }
        $('#searchBtn').prop('disabled', false);
        $('#cancelBtn').hide();
        $('#progressBar').hide();
        $('#progressText').hide();
        $('#resultsBody').html('<tr><td colspan="5" style="text-align: center;">Search cancelled</td></tr>');
    });

    function performBulkKO() {
        const defender = $('#defender').val();
        if (!defender) {
            alert('Please select a defender Pokemon');
            return;
        }

        // Collect form data using the same Field controls as the calculator.
        const data = {
            defender: defender,
            defender_item: $('#defender_item').val() || null,
            defender_ability: $('#defender_ability').val() || null,
            defender_hp: $('#defender_hp').val() ? parseInt($('#defender_hp').val()) : null,
            defender_def: $('#defender_def').val() ? parseInt($('#defender_def').val()) : null,
            defender_spd: $('#defender_spd').val() ? parseInt($('#defender_spd').val()) : null,
            move: $('#move').val() || null,
            attacker_item: $('#attacker_item').val() || null,
            positive_nature: $('#attacker_nature').val() === '1.1',
            percent: $('#ko_percent').val() ? parseFloat($('#ko_percent').val()) : 100.0,
            filter_type1: $('#filter_type1').val() || null,
            filter_min_bst: $('#filter_min_bst').val() ? parseInt($('#filter_min_bst').val()) : null,
            filter_min_spe: $('#filter_min_spe').val() ? parseInt($('#filter_min_spe').val()) : null,
            only_super_effective: $('#only_super_effective').is(':checked'),
            terrain: $('input[name="terrain"]:checked').val() || null,
            weather: $('input[name="weather"]:checked').val() || null,
            field: $('input[name="fieldState"]:checked').map(function() { return this.value; }).get(),
            format: $('input[name="format"]:checked').val() || 'doubles',
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

        console.log('Sending data:', data);

        // Show loading state
        $('#searchBtn').prop('disabled', true);
        $('#cancelBtn').show();
        $('#progressBar').show();
        $('#progressFill').css('width', '0%');
        $('#progressText').show().text('Initializing...');
        $('#resultsBody').empty();
        $('#resultsCount').text('0 results');

        // Use Server-Sent Events for real-time progress
        const queryString = $.param(data);
        window.eventSource = new EventSource('/api/bulk-ko-stream?' + queryString);

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
            } else if (msg.type === 'batch_results') {
                // Display all results at once (for specific move mode)
                displayResults(msg.results);
            } else if (msg.type === 'complete') {
                window.eventSource.close();
                window.eventSource = null;
                $('#progressFill').css('width', '100%');
                $('#searchBtn').prop('disabled', false);
                $('#cancelBtn').hide();

                if (!msg.success) {
                    $('#resultsBody').html('<tr><td colspan="5" style="text-align: center; color: red;">Error: ' + msg.error + '</td></tr>');
                    $('#resultsCount').text('');
                } else if ($('#resultsBody tr').length === 0) {
                    // No results found
                    $('#resultsBody').html('<tr><td colspan="5" style="text-align: center;">No attackers found that can KO this defender</td></tr>');
                }

                setTimeout(function() {
                    $('#progressBar').hide();
                    $('#progressText').hide();
                }, 1000);
            }
        };

        window.eventSource.onerror = function() {
            window.eventSource.close();
            window.eventSource = null;
            $('#searchBtn').prop('disabled', false);
            $('#cancelBtn').hide();
            $('#progressBar').hide();
            $('#progressText').hide();
            $('#resultsBody').html('<tr><td colspan="5" style="text-align: center; color: red;">Connection error</td></tr>');
        };
    }

    function displayResults(results) {
        if (results.length === 0) {
            $('#resultsBody').html('<tr><td colspan="5" style="text-align: center;">No attackers found that can KO this defender</td></tr>');
            $('#resultsCount').text('0 results');
            return;
        }

        $('#resultsCount').text(results.length + ' result' + (results.length !== 1 ? 's' : ''));

        // Sort by points (ascending)
        results.sort(function(a, b) {
            return a.points - b.points;
        });

        let html = '';
        results.forEach(result => {
            const ability = result.ability || 'Any';
            html += `
                <tr>
                    <td>${esc(result.name)}</td>
                    <td>${result.points}</td>
                    <td>${esc(result.move)}</td>
                    <td class="${ability === 'Any' ? 'ability-not-required' : ''}">${esc(ability)}</td>
                    <td>${window.bulkResultDescription(result.desc, fairyAuraActive)}</td>
                </tr>
            `;
        });

        $('#resultsBody').html(html);
    }

    function appendResult(result) {
        // Get current count
        const currentCount = $('#resultsBody tr').length;
        $('#resultsCount').text(currentCount + ' result' + (currentCount !== 0 ? 's' : ''));

        // Append the new result
        const ability = result.ability || 'Any';
        const row = `
            <tr>
                <td>${esc(result.name)}</td>
                <td>${result.points}</td>
                <td>${esc(result.move)}</td>
                <td class="${ability === 'Any' ? 'ability-not-required' : ''}">${esc(ability)}</td>
                <td>${window.bulkResultDescription(result.desc, fairyAuraActive)}</td>
            </tr>
        `;
        $('#resultsBody').append(row);
    }

    function esc(value) {
        return $('<div>').text(value == null ? '' : value).html();
    }
});
