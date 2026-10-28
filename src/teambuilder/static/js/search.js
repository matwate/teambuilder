$(document).ready(function() {
    // Page navigation handlers
    $('#page-calculator').change(function() {
        if ($(this).is(':checked')) {
            window.location.href = '/';
        }
    });

    $('#page-search').change(function() {
        if ($(this).is(':checked')) {
            // Already on search page
        }
    });

    $('#page-bulk-ko').change(function() {
        if ($(this).is(':checked')) {
            window.location.href = '/bulk-ko';
        }
    });

    $('#page-bulk-survive').change(function() {
        if ($(this).is(':checked')) {
            window.location.href = '/bulk-survive';
        }
    });

    // Initialize Select2 for move input
    $('#move').select2({
        placeholder: 'e.g., Earthquake',
        allowClear: true,
        width: '100%',
        dropdownParent: $('.filter-section:has(#move)')
    });

    // Type color mapping
    const typeColors = {
        'Normal': '#A8A878',
        'Fire': '#F08030',
        'Water': '#6890F0',
        'Electric': '#F8D030',
        'Grass': '#78C850',
        'Ice': '#98D8D8',
        'Fighting': '#C03028',
        'Poison': '#A040A0',
        'Ground': '#E0C068',
        'Flying': '#A890F0',
        'Psychic': '#F85888',
        'Bug': '#A8B820',
        'Rock': '#B8A038',
        'Ghost': '#705898',
        'Dragon': '#7038F8',
        'Dark': '#705848',
        'Steel': '#B8B8D0',
        'Fairy': '#EE99AC'
    };

    // Store all Pokemon data
    let allPokemon = [];
    let allMoves = [];
    let currentSort = { column: null, direction: 'asc' };

    // Load all Pokemon and moves on page load
    function loadAllData() {
        // Load all Pokemon
        $.ajax({
            url: '/api/search',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({}),
            success: function(response) {
                if (response.success) {
                    allPokemon = response.results;
                    performClientSearch();
                }
            }
        });

        // Load all moves
        $.get('/api/moves', function(data) {
            allMoves = data;
            data.forEach(function(move) {
                $('#move').append('<option value="' + move + '">' + move + '</option>');
            });
            $('#move').val(null).trigger('change');
        });
    }

    // Search button click handler
    $('#searchBtn').click(function() {
        performClientSearch();
    });

    // Auto-filter on any input change
    $('.filter-group input, .filter-group select').on('input change', function() {
        performClientSearch();
    });

    // Select2 change event for move dropdown
    $('#move').on('change', function() {
        performClientSearch();
    });

    // Debounce for number inputs
    let debounceTimer;
    $('.filter-group input[type="number"]').on('input', function() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(function() {
            performClientSearch();
        }, 100);
    });

    // Sort handler for table headers
    $('.results-table th').click(function() {
        const column = $(this).data('column');
        if (!column) return;

        if (currentSort.column === column) {
            currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
        } else {
            currentSort.column = column;
            currentSort.direction = 'asc';
        }

        // Update sort indicators
        $('.results-table th').removeClass('sort-asc sort-desc');
        $(this).addClass(currentSort.direction === 'asc' ? 'sort-asc' : 'sort-desc');

        performClientSearch();
    });

    function performClientSearch() {
        // Collect filter values
        const type1Val = $('#type1').val();
        const type2Val = $('#type2').val();
        const moveVal = $('#move').val();

        const filters = {
            type1: (type1Val && type1Val !== '') ? type1Val : null,
            type2: (type2Val && type2Val !== '') ? type2Val : null,
            hp_min: $('#hp_min').val() ? parseInt($('#hp_min').val()) : null,
            hp_max: $('#hp_max').val() ? parseInt($('#hp_max').val()) : null,
            atk_min: $('#atk_min').val() ? parseInt($('#atk_min').val()) : null,
            atk_max: $('#atk_max').val() ? parseInt($('#atk_max').val()) : null,
            defender_min: $('#defender_min').val() ? parseInt($('#defender_min').val()) : null,
            defender_max: $('#defender_max').val() ? parseInt($('#defender_max').val()) : null,
            spa_min: $('#spa_min').val() ? parseInt($('#spa_min').val()) : null,
            spa_max: $('#spa_max').val() ? parseInt($('#spa_max').val()) : null,
            spd_min: $('#spd_min').val() ? parseInt($('#spd_min').val()) : null,
            spd_max: $('#spd_max').val() ? parseInt($('#spd_max').val()) : null,
            spe_min: $('#spe_min').val() ? parseInt($('#spe_min').val()) : null,
            spe_max: $('#spe_max').val() ? parseInt($('#spe_max').val()) : null,
            bst_min: $('#bst_min').val() ? parseInt($('#bst_min').val()) : null,
            bst_max: $('#bst_max').val() ? parseInt($('#bst_max').val()) : null,
            move: (moveVal && moveVal !== '') ? moveVal : null
        };

        // If move filter is set, use server-side search
        if (filters.move) {
            performServerSearch(filters);
            return;
        }

        // Filter Pokemon client-side
        let filtered = allPokemon.filter(pokemon => {
            // Type filters - match regardless of order
            if (filters.type1 && filters.type2) {
                // Both types selected - Pokemon must have both types in any order
                const hasType1 = pokemon.type1 === filters.type1 || pokemon.type2 === filters.type1;
                const hasType2 = pokemon.type1 === filters.type2 || pokemon.type2 === filters.type2;
                if (!hasType1 || !hasType2) return false;
            } else if (filters.type1) {
                // Only type1 selected - Pokemon must have this type in either position
                if (pokemon.type1 !== filters.type1 && pokemon.type2 !== filters.type1) return false;
            } else if (filters.type2) {
                // Only type2 selected - Pokemon must have this type in either position
                if (pokemon.type1 !== filters.type2 && pokemon.type2 !== filters.type2) return false;
            }

            // Stat filters
            if (filters.hp_min !== null && pokemon.hp < filters.hp_min) return false;
            if (filters.hp_max !== null && pokemon.hp > filters.hp_max) return false;
            if (filters.atk_min !== null && pokemon.atk < filters.atk_min) return false;
            if (filters.atk_max !== null && pokemon.atk > filters.atk_max) return false;
            if (filters.defender_min !== null && pokemon.def < filters.defender_min) return false;
            if (filters.defender_max !== null && pokemon.def > filters.defender_max) return false;
            if (filters.spa_min !== null && pokemon.spa < filters.spa_min) return false;
            if (filters.spa_max !== null && pokemon.spa > filters.spa_max) return false;
            if (filters.spd_min !== null && pokemon.spd < filters.spd_min) return false;
            if (filters.spd_max !== null && pokemon.spd > filters.spd_max) return false;
            if (filters.spe_min !== null && pokemon.spe < filters.spe_min) return false;
            if (filters.spe_max !== null && pokemon.spe > filters.spe_max) return false;
            if (filters.bst_min !== null && pokemon.bst < filters.bst_min) return false;
            if (filters.bst_max !== null && pokemon.bst > filters.bst_max) return false;

            return true;
        });

        // Apply sorting
        if (currentSort.column) {
            filtered.sort((a, b) => {
                let aVal = a[currentSort.column];
                let bVal = b[currentSort.column];

                // Handle string comparison for name
                if (typeof aVal === 'string') {
                    aVal = aVal.toLowerCase();
                    bVal = bVal.toLowerCase();
                }

                if (aVal < bVal) return currentSort.direction === 'asc' ? -1 : 1;
                if (aVal > bVal) return currentSort.direction === 'asc' ? 1 : -1;
                return 0;
            });
        }

        displayResults(filtered);
    }

    function performServerSearch(filters) {
        $.ajax({
            url: '/api/search',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(filters),
            success: function(response) {
                if (response.success) {
                    displayResults(response.results);
                } else {
                    $('#resultsBody').html('<tr><td colspan="10" style="text-align: center; color: red;">Error: ' + response.error + '</td></tr>');
                    $('#resultsCount').text('');
                }
            },
            error: function(xhr, status, error) {
                $('#resultsBody').html('<tr><td colspan="10" style="text-align: center; color: red;">Error: ' + error + '</td></tr>');
                $('#resultsCount').text('');
            }
        });
    }

    function displayResults(results) {
        if (results.length === 0) {
            $('#resultsBody').html('<tr><td colspan="10" style="text-align: center;">No Pokemon found matching filters</td></tr>');
            $('#resultsCount').text('0 results');
            return;
        }

        $('#resultsCount').text(results.length + ' result' + (results.length !== 1 ? 's' : ''));

        let html = '';
        results.forEach(pokemon => {
            const type1Color = typeColors[pokemon.type1] || '#888';
            const type2Color = pokemon.type2 ? (typeColors[pokemon.type2] || '#888') : null;

            const typeBadges = pokemon.type2
                ? `<span class="type-badge" style="background: ${type1Color};">${pokemon.type1}</span><span class="type-badge" style="background: ${type2Color};">${pokemon.type2}</span>`
                : `<span class="type-badge" style="background: ${type1Color};">${pokemon.type1}</span>`;

            html += `
                <tr>
                    <td>${pokemon.name}</td>
                    <td>${typeBadges}</td>
                    <td>${pokemon.hp}</td>
                    <td>${pokemon.atk}</td>
                    <td>${pokemon.def}</td>
                    <td>${pokemon.spa}</td>
                    <td>${pokemon.spd}</td>
                    <td>${pokemon.spe}</td>
                    <td>${pokemon.bst}</td>
                </tr>
            `;
        });

        $('#resultsBody').html(html);
    }

    // Load data on page load
    loadAllData();
});
