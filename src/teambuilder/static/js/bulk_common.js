$(document).ready(function() {
    const abilityToFieldEffect = {
        'Drought': { group: 'weather', value: 'Sun' },
        'Drizzle': { group: 'weather', value: 'Rain' },
        'Sand Stream': { group: 'weather', value: 'Sand' },
        'Snow Warning': { group: 'weather', value: 'Snow' },
        'Electric Surge': { group: 'terrain', value: 'Electric' },
        'Grassy Surge': { group: 'terrain', value: 'Grassy' },
        'Misty Surge': { group: 'terrain', value: 'Misty' },
        'Psychic Surge': { group: 'terrain', value: 'Psychic' },
        'Fairy Aura': { group: 'fieldState', value: 'FairyAura' }
    };

    const megaStones = {
        'Venusaur-Mega': 'Venusaurite',
        'Charizard-Mega X': 'Charizardite X',
        'Charizard-Mega Y': 'Charizardite Y',
        'Blastoise-Mega': 'Blastoisinite',
        'Beedrill-Mega': 'Beedrillite',
        'Pidgeot-Mega': 'Pidgeotite',
        'Raichu-Mega X': 'Raichunite X',
        'Raichu-Mega Y': 'Raichunite Y',
        'Clefable-Mega': 'Clefablite',
        'Alakazam-Mega': 'Alakazite',
        'Victreebel-Mega': 'Victreebelite',
        'Slowbro-Mega': 'Slowbronite',
        'Gengar-Mega': 'Gengarite',
        'Kangaskhan-Mega': 'Kangaskhanite',
        'Starmie-Mega': 'Starminite',
        'Pinsir-Mega': 'Pinsirite',
        'Gyarados-Mega': 'Gyaradosite',
        'Aerodactyl-Mega': 'Aerodactylite',
        'Dragonite-Mega': 'Dragoninite',
        'Meganium-Mega': 'Meganiumite',
        'Feraligatr-Mega': 'Feraligite',
        'Ampharos-Mega': 'Ampharosite',
        'Steelix-Mega': 'Steelixite',
        'Scizor-Mega': 'Scizorite',
        'Heracross-Mega': 'Heracronite',
        'Skarmory-Mega': 'Skarmorite',
        'Houndoom-Mega': 'Houndoominite',
        'Tyranitar-Mega': 'Tyranitarite',
        'Sceptile-Mega': 'Sceptilite',
        'Blaziken-Mega': 'Blazikenite',
        'Swampert-Mega': 'Swampertite',
        'Gardevoir-Mega': 'Gardevoirite',
        'Sableye-Mega': 'Sablenite',
        'Mawile-Mega': 'Mawilite',
        'Aggron-Mega': 'Aggronite',
        'Medicham-Mega': 'Medichamite',
        'Manectric-Mega': 'Manectrite',
        'Sharpedo-Mega': 'Sharpedonite',
        'Camerupt-Mega': 'Cameruptite',
        'Altaria-Mega': 'Altarianite',
        'Banette-Mega': 'Banettite',
        'Chimecho-Mega': 'Chimechite',
        'Absol-Mega': 'Absolite',
        'Absol-Mega Z': 'Absolite Z',
        'Glalie-Mega': 'Glalitite',
        'Salamence-Mega': 'Salamencite',
        'Metagross-Mega': 'Metagrossite',
        'Staraptor-Mega': 'Staraptite',
        'Lopunny-Mega': 'Lopunnite',
        'Garchomp-Mega': 'Garchompite',
        'Garchomp-Mega Z': 'Garchompite Z',
        'Lucario-Mega': 'Lucarionite',
        'Lucario-Mega Z': 'Lucarionite Z',
        'Abomasnow-Mega': 'Abomasite',
        'Gallade-Mega': 'Galladite',
        'Froslass-Mega': 'Froslassite',
        'Emboar-Mega': 'Emboarite',
        'Excadrill-Mega': 'Excadrite',
        'Audino-Mega': 'Audinite',
        'Scolipede-Mega': 'Scolipite',
        'Scrafty-Mega': 'Scraftinite',
        'Eelektross-Mega': 'Eelektrossite',
        'Chandelure-Mega': 'Chandelurite',
        'Golurk-Mega': 'Golurkite',
        'Chesnaught-Mega': 'Chesnaughtite',
        'Delphox-Mega': 'Delphoxite',
        'Greninja-Mega': 'Greninjite',
        'Pyroar-Mega': 'Pyroarite',
        'Floette-Mega': 'Floettite',
        'Meowstic-M-Mega': 'Meowsticite',
        'Meowstic-F-Mega': 'Meowsticite',
        'Malamar-Mega': 'Malamarite',
        'Barbaracle-Mega': 'Barbaracite',
        'Dragalge-Mega': 'Dragalgite',
        'Hawlucha-Mega': 'Hawluchanite',
        'Crabominable-Mega': 'Crabominite',
        'Golisopod-Mega': 'Golisopite',
        'Drampa-Mega': 'Drampanite',
        'Falinks-Mega': 'Falinksite',
        'Scovillain-Mega': 'Scovillainite',
        'Glimmora-Mega': 'Glimmoranite',
        'Baxcalibur-Mega': 'Baxcalibrite'
    };

    $('.item').on('items-loaded', function() {
        $(this).data('allItemOptions', $(this).children().clone());
    });

    $('.item').on('select2:opening', function(event) {
        if ($(this).data('requiredMegaStone')) {
            event.preventDefault();
        }
    }).on('change', function() {
        const $item = $(this);
        const requiredStone = $item.data('requiredMegaStone');
        if (requiredStone && $item.val() !== requiredStone) {
            $item.val(requiredStone).trigger('change');
        }
    });

    const pokemonItemBindings = {
        'attacker-input': '#itemL1',
        'defender-input': '#itemR1',
        'attacker': '#attacker_item',
        'defender': '#defender_item'
    };

    $(document).on('change', '#attacker-input, #defender-input, #attacker, #defender', function() {
        const $pokemon = $(this);
        const $item = $(pokemonItemBindings[this.id]);
        const options = $item.data('allItemOptions');
        if (!options) {
            return;
        }

        const stone = megaStones[$pokemon.val()];
        $item
            .empty()
            .append(options.clone())
            .prop('disabled', false);
        if (!stone) {
            $item.data('requiredMegaStone', null).val('');
            $item.trigger('change');
            return;
        }

        const $stone = $item.find('option').filter(function() {
            return this.value === stone;
        });
        if (!$stone.length) {
            console.error(`Required Mega Stone "${stone}" is missing for ${$pokemon.val()}.`);
            $item.data('requiredMegaStone', null).val('');
            $item.trigger('change');
            return;
        }

        $item.data('requiredMegaStone', stone);
        $item.val(stone).trigger('change');
    });

    $('.ability').on('change', function() {
        const $ability = $(this);
        const previous = $ability.data('fieldEffect');
        const effect = abilityToFieldEffect[$ability.val()];
        if (previous) {
            const $previous = $(`input[name="${previous.group}"][value="${previous.value}"]`);
            const stillProvidedByOtherAbility = $('.ability').not($ability).toArray().some(function(select) {
                const otherEffect = abilityToFieldEffect[$(select).val()];
                return otherEffect &&
                    otherEffect.group === previous.group &&
                    otherEffect.value === previous.value;
            });
            if ($previous.is(':checked') && !stillProvidedByOtherAbility) {
                if (previous.group === 'fieldState') {
                    $previous.prop('checked', false);
                } else {
                    $(`input[name="${previous.group}"][value=""]`).prop('checked', true);
                }
            }
        }
        if (effect) {
            $(`input[name="${effect.group}"][value="${effect.value}"]`).prop('checked', true);
        }
        $ability.data('fieldEffect', effect || null);
    });
});

window.bulkResultDescription = function(desc, fairyAuraActive) {
    const escaped = $('<div>').text(desc == null ? '' : desc).html();
    if (!fairyAuraActive) {
        return escaped;
    }

    return escaped + '<br><span class="field-condition-note">Fairy Aura is active; the damage calculator omits it from this description (issue #348).</span>';
};
