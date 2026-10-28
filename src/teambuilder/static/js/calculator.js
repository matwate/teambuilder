$(document).ready(function () {
	let lastResults = null; // results from the most recent calculation
	let currentMoveCategory = null; // track current move category
	let isLoadingMoveCategory = false; // track if we're loading move category

	const calculators = {KO: "ko", SURVIVAL: "survival"};
	let currentCalculator = calculators.KO; //initialize as KO calculator

	function setupCalculator(calculator) {
		const isKoCalculator = calculator === calculators.KO;
		currentCalculator = calculator;
		
		// Attacker nature
		isKoCalculator ? $("#attacker-nature-header").show() : $("#attacker-nature-header").hide();
		isKoCalculator ? $("#attacker-nature-input").show() : $("#attacker-nature-input").hide();

		// Attacker EVs
		isKoCalculator ? $("#attacker-evs-header").hide() : $("#attacker-evs-header").show();
		isKoCalculator ? $("#attacker-evs-input").hide() : $("#attacker-evs-input").show();

		// +/- nature Notes
		isKoCalculator ? $("#attacker-note-survival").hide() : $("#attacker-note-survival").show();
		isKoCalculator ? $("#defender-note-survival").show() : $("#defender-note-survival").hide();

		// Defender HP
		isKoCalculator ? $("#defender-hp-header").show() : $("#defender-hp-header").hide();
		isKoCalculator ? $("#defender-hp-input").show() : $("#defender-hp-input").hide();

		// Defender EVs
		isKoCalculator ? $("#defender-evs-header").show() : $("#defender-evs-header").hide();
		isKoCalculator ? $("#defender-evs-input").show() : $("#defender-evs-input").hide();

		// Defender nature
		isKoCalculator ? $("#defender-nature-header").hide() : $("#defender-nature-header").show();
		isKoCalculator ? $("#defender-nature-input").hide() : $("#defender-nature-input").show();

		$("#mainResult").text("Select Pokemon and Move to Calculate");
		$("#resultTable").empty();
		$("#calcHeader").text("");
		lastResults = null;		
	}

	// Setup the initial state of the calculator
	$("#survival-calc").prop("checked", false);
	$("#ko-calc").prop("checked", true);
	$("#allResults").prop("checked", true);
	setupCalculator(calculators.KO);

	// Page navigation handlers
	$('#page-calculator').change(function() {
		if ($(this).is(':checked')) {
			// Already on calculator page
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
			window.location.href = '/bulk-survive';
		}
	});

	// Helper function to initialize Select2
	function initSelect2($element, placeholder, options = {}) {
		const defaultOptions = {
			placeholder: placeholder,
			allowClear: true,
			dropdownAutoWidth: true,
			width: "style",
		};
		$element.select2({ ...defaultOptions, ...options });
	}

	// Helper function to populate dropdown with items
	function populateDropdown($element, items, emptyOption = null) {
		$element.empty();
		if (emptyOption) {
			$element.append($("<option>", { value: emptyOption.value, text: emptyOption.text }));
		}
		items.forEach((item) => {
			if (emptyOption && item === emptyOption.value) return;
			const text = item === "" ? "None" : item;
			$element.append($("<option>", { value: item, text: text }));
		});
	}

	// Helper function to collect checkbox values
	function collectCheckboxValues(selector) {
		const values = [];
		$(selector + ":checked").each(function () {
			values.push($(this).val());
		});
		return values;
	}

	// Helper function to get radio value or default
	function getRadioValue(name, defaultValue = "") {
		return $(`input[name="${name}"]:checked`).val() || defaultValue;
	}

	// Helper function to load and populate abilities
	function loadAbilities(pokemon, $abilitySelect) {
		$.get(
			"/api/abilities/" + encodeURIComponent(pokemon),
			function (abilities) {
				populateDropdown($abilitySelect, abilities, { value: "", text: "None" });
				if (abilities.length === 1) {
					$abilitySelect.val(abilities[0]).trigger("change");
				} else {
					$abilitySelect.val("").trigger("change");
				}
			}
		);
	}

	function renderResults() {
		const $table = $("#resultTable").empty();
		if (!lastResults || lastResults.length === 0) return;

		const esc = (s) => $("<div>").text(s).html();
		const minPoints = Math.min(...lastResults.map((r) => r.points));
		$("#mainResult").text(minPoints + " points");

		const rows = lastResults

		if (currentCalculator === "ko") {
			// For KO calculator, we show attacking stat investment
			let html =
				'<tr><th class="num">Points</th><th class="num">Investment</th>' +
				'<th>Damage</th><th>Result</th></tr>';

			rows.forEach((r) => {
				const dmg = r.damage[0] + "-" + r.damage[1];
				const pct = "(" + r.percent[0] + " - " + r.percent[1] + "%)";
				const ko = r.desc.split(" -- ")[1] || "";

				html +=
					"<tr" +
					(r.points === minPoints ? ' class="min"' : "") +
					">" +
					'<td class="num">' +
					r.points +
					"</td>" +
					'<td class="num">' +
					r.desc +
					"</td>" +
					"<td>" +
					dmg +
					" " +
					pct +
					"</td>" +
					"<td>" +
					esc(ko) +
					"</td>" +
					"</tr>";
			});

			$table.html(html);
		} else {
			// Survival calculator
			// Which defensive stat was invested in: the spread key that isn't hp
			const defKey = rows[0].spread
				? Object.keys(rows[0].spread).find((k) => k !== "hp")
				: null;
			const defLabel = defKey === "spd" ? "SpD" : "Def";

			let html =
				'<tr><th class="num">Points</th><th class="num">HP</th>' +
				'<th class="num">' +
				defLabel +
				"</th><th>Damage</th><th>Result</th></tr>";

			rows.forEach((r) => {
				const hpEv = r.spread ? r.spread.hp : "?";
				const defEv = r.spread && defKey ? r.spread[defKey] : "?";
				const dmg = r.damage[0] + "-" + r.damage[1];
				const pct = "(" + r.percent[0] + " - " + r.percent[1] + "%)";
				const ko = r.desc.split(" -- ")[1] || "";

				html +=
					"<tr" +
					(r.points === minPoints ? ' class="min"' : "") +
					">" +
					'<td class="num">' +
					r.points +
					"</td>" +
					'<td class="num">' +
					hpEv +
					"</td>" +
					'<td class="num">' +
					defEv +
					"</td>" +
					"<td>" +
					dmg +
					" " +
					pct +
					"</td>" +
					"<td>" +
					esc(ko) +
					"</td>" +
					"</tr>";
			});

			$table.html(html);
		}
	}

	// Toggle between KO and Survival calculators
	$("#ko-calc").on("change", function () {
		if ($(this).is(":checked")) {
			setupCalculator(calculators.KO);
		}
	});

	$("#survival-calc").on("change", function () {
		if ($(this).is(":checked")) {
			setupCalculator(calculators.SURVIVAL);
		}
	});

	// Toggle between modes without a manual re-calculate (survival only)
	$("#minOnly").on("change", function () {
		if (lastResults) renderResults();
	});

	$("#allResults").on("change", function () {
		if (lastResults) renderResults();
	});

	// Initialize Select2 for Pokemon dropdowns
	$("#attacker-input").select2({
		placeholder: "Select Pokemon",
		allowClear: true,
		width: "100%",
	});

	$("#defender-input").select2({
		placeholder: "Select Pokemon",
		allowClear: true,
		width: "100%",
	});

	// Initialize Select2 for other dropdowns using helper
	initSelect2($("#move-select"), "Select Move");
	initSelect2($("#abilityL1"), "Select Ability");
	initSelect2($("#abilityR1"), "Select Ability");
	initSelect2($("#itemL1"), "Select Item");
	initSelect2($("#itemR1"), "Select Item");

	// Load Pokemon list from Python backend
	$.get("/api/pokemon", function (pokemon) {
		pokemon.forEach((p) => {
			$("#attacker-input").append(
				$("<option>", { value: p, text: p }),
			);
			$("#defender-input").append(
				$("<option>", { value: p, text: p }),
			);
		});
	});

	// Load items
	$.get("/api/items", function (items) {
		populateDropdown($("#itemL1"), items, { value: "", text: "Select Item" });
		populateDropdown($("#itemR1"), items, { value: "", text: "Select Item" });
		$("#itemL1").val("").trigger("change");
		$("#itemR1").val("").trigger("change");
		$(".item").trigger("items-loaded");
	});

	// Load moves when attacker is selected
	$("#attacker-input").on("change", function () {
		const pokemon = $(this).val();
		$("#move-select")
			.empty()
			.append($("<option>", { value: "", text: "Select Move" }))
			.val("")
			.trigger("change");
		$("#itemL1").val("").trigger("change");
		$("#abilityL1")
			.empty()
			.append($("<option>", { value: "", text: "Any" }))
			.val("")
			.trigger("change");
		if (pokemon) {
			$.get(
				"/api/moves/" + encodeURIComponent(pokemon),
				function (moves) {
					populateDropdown($("#move-select"), moves, { value: "", text: "Select Move" });
					$("#move-select").val("").trigger("change");
					loadAbilities(pokemon, $("#abilityL1"));
					updateCalcHeader();
				}
			);
		} else {
			updateCalcHeader();
		}
	});

	// Get move category when move is selected
	$("#move-select").on("change", function () {
		const move = $(this).val();
		if (move) {
			isLoadingMoveCategory = true;
			$.get(
				"/api/move-category/" + encodeURIComponent(move),
				function (data) {
					currentMoveCategory = data.category;
					isLoadingMoveCategory = false;
					updateCalcHeader();
				}
			).fail(function () {
				currentMoveCategory = null;
				isLoadingMoveCategory = false;
				updateCalcHeader();
			});
		} else {
			currentMoveCategory = null;
			isLoadingMoveCategory = false;
			updateCalcHeader();
		}
	});

	// Load defender abilities
	$("#defender-input").on("change", function () {
		const pokemon = $(this).val();
		$("#itemR1").val("").trigger("change");
		$("#abilityR1")
			.empty()
			.append($("<option>", { value: "", text: "Any" }))
			.val("")
			.trigger("change");
		if (pokemon) {
			loadAbilities(pokemon, $("#abilityR1"));
		}
	});

	// Function to update the calculation header
	function updateCalcHeader() {
		const attacker = $("#attacker-input").val() || "";
		const move = $("#move-select").val() || "";
		const attackerBoost = $("#attacker-boost").val();
		const defender = $("#defender-input").val() || "";
		const defenderAbility = $("#abilityR1").val() || "";
		const weather = getRadioValue("weather");

		// If move is empty, show blank header
		if (!move) {
			$("#calcHeader").text("");
			return;
		}

		// If we're still loading move category, don't update yet
		if (isLoadingMoveCategory) {
			return;
		}

		let boostText = "";
		if (attackerBoost != 0) {
			boostText = (attackerBoost > 0 ? "+" : "") + attackerBoost + " ";
		}

		// Add defender ability if present
		let defenderText = defender;
		if (defenderAbility) {
			defenderText = `${defenderAbility} ${defender}`;
		}

		// Add weather if present
		let weatherText = "";
		if (weather) {
			weatherText = ` in ${weather}`;
		}

		if (currentCalculator === "ko") {
			const attackerNature = $("#attacker-nature").val();
			const defenderHp = $("#defender-hp").val();
			const defenderEvs = $("#defender-evs").val();

			// Use ATK or SPA based on move category
			let statText = "";
			if (currentMoveCategory) {
				const statLabel = currentMoveCategory === "Physical" ? "Atk" : "SpA";
				statText = statLabel;
			}

			// Add attacker nature if not neutral
			if (attackerNature !== "1.0") {
				const natureText = attackerNature === "1.1" ? "+" : "-";
				statText += natureText;
			}

			// Format move (without BP and type)
			let moveText = move;

			// Add defender stats if any are non-zero
			let defenderStats = [];
			if (defenderHp && defenderHp != 0) defenderStats.push(`${defenderHp} HP`);
			if (defenderEvs && defenderEvs != 0) defenderStats.push(`${defenderEvs} Def/SpD`);
			if (defenderStats.length > 0) {
				defenderText += ` (${defenderStats.join(", ")})`;
			}

			const headerText = `${boostText}${statText} ${attacker} ${moveText} vs. ${defenderText}${weatherText}`;
			$("#calcHeader").text(headerText);
		} else {
			// Survival calculator
			const attackerEvs = $("#attacker-evs").val();
			const defenderNature = $("#defender-nature").val();

			// Use ATK or SPA based on move category
			let evsText = attackerEvs;
			if (currentMoveCategory) {
				const statLabel = currentMoveCategory === "Physical" ? "Atk" : "SpA";
				evsText = attackerEvs + " " + statLabel;
			}

			// Format move (without BP and type)
			let moveText = move;

			// Add defender nature if not neutral
			if (defenderNature !== "1.0") {
				const natureText = defenderNature === "1.1" ? "+" : "-";
				defenderText = `${natureText}${defenderText}`;
			}

			const headerText = `${boostText}${evsText} ${attacker} ${moveText} vs. ${defenderText}${weatherText}`;
			$("#calcHeader").text(headerText);
		}
	}

	// Bind inputs to update calculation header
	$("#attacker-boost").on("change", updateCalcHeader);
	$("#attacker-nature").on("change", updateCalcHeader);
	$("#attacker-evs").on("input", updateCalcHeader);
	$("#itemL1").on("change", updateCalcHeader);
	$("#defender-input").on("change", updateCalcHeader);
	$("#abilityR1").on("change", updateCalcHeader);
	$("#defender-hp").on("input", updateCalcHeader);
	$("#defender-evs").on("input", updateCalcHeader);
	$("#defender-nature").on("change", updateCalcHeader);
	$('input[name="weather"]').on("change", updateCalcHeader);

	// Remove error highlighting when user interacts with required fields
	$("#attacker-input").on("change", function () {
		$(this).siblings(".select2-container").removeClass("input-error");
	});
	$("#move-select").on("change", function () {
		$(this).siblings(".select2-container").removeClass("input-error");
	});
	$("#defender-input").on("change", function () {
		$(this).siblings(".select2-container").removeClass("input-error");
	});

	// Initialize header
	updateCalcHeader();

	// Hide tooltip initially
	$("#tooltipText").hide();

	// Calculate button
	$("#calculate-btn").on("click", function () {
		const attacker = $("#attacker-input").val();
		const move = $("#move-select").val();
		const defender = $("#defender-input").val();

		// Remove any existing error highlighting
		$("#attacker-input").siblings(".select2-container").removeClass("input-error");
		$("#move-select").siblings(".select2-container").removeClass("input-error");
		$("#defender-input").siblings(".select2-container").removeClass("input-error");

		// Check required fields
		let hasError = false;
		if (!attacker) {
			$("#attacker-input").siblings(".select2-container").addClass("input-error");
			hasError = true;
		}
		if (!move) {
			$("#move-select").siblings(".select2-container").addClass("input-error");
			hasError = true;
		}
		if (!defender) {
			$("#defender-input").siblings(".select2-container").addClass("input-error");
			hasError = true;
		}

		if (hasError) {
			return;
		}

		let data = {
			attacker: attacker,
			move: move,
			defender: defender,
			percent: parseFloat($("#percent").val()),
			attacker_ability: $("#abilityL1").val(),
			attacker_item: $("#itemL1").val(),
			attacker_boost: $("#attacker-boost").val(),
			defender_boost: $("#defender-boost").val(),
			defender_ability: $("#abilityR1").val(),
			defender_item: $("#itemR1").val(),
			format: getRadioValue("format", "doubles"),
			terrain: getRadioValue("terrain"),
			weather: getRadioValue("weather"),
			field: collectCheckboxValues('input[name="fieldState"]'),
			spikes: getRadioValue("spikes", "0"),
			isSR: $("#SR").is(":checked"),
			isReflect: $("#reflect").is(":checked"),
			isLightScreen: $("#lightScreen").is(":checked"),
			isAuroraVeil: $("#auroraVeil").is(":checked"),
			isFriendGuard: $("#friendGuard").is(":checked"),
			isProtect: $("#protect").is(":checked"),
			isLeechSeed: $("#leechSeed").is(":checked"),
			isSaltCure: $("#saltCure").is(":checked"),
			isCharge: $("#charge").is(":checked"),
			isHelpingHand: $("#helpingHand").is(":checked"),
			isPowerTrickLeft: $("#powerTrickL").is(":checked"),
			isPowerTrickRight: $("#powerTrickR").is(":checked"),
		};

		if (currentCalculator === "ko") {
			data.attacker_nature = $("#attacker-nature").val();
			data.defender_hp = $("#defender-hp").val();
			data.defender_evs = $("#defender-evs").val();
		} else { // survival
			data.attacker_evs = $("#attacker-evs").val();
			data.defender_nature = $("#defender-nature").val();
		}

		console.log("Sending data:", data);
		$("#mainResult").text("Calculating...");
		const apiUrl = currentCalculator === "ko" ? "/api/ko-calculation" : "/api/survival";

		$.ajax({
			url: apiUrl,
			method: "POST",
			contentType: "application/json",
			dataType: "json",
			data: JSON.stringify(data),
			success: function (result) {
				const $table = $("#resultTable").empty();

				if (!result.success) {
					$("#mainResult").text(result.message);
					return;
				}

				if (result.results.length === 0) {
					$("#mainResult").text("No viable spread found");
					return;
				}

				lastResults = result.results;

				// Update header with the first result's description
				if (result.results.length > 0) {
					const firstDesc = result.results[0].desc;
					if (currentCalculator === "ko") {
						$("#calcHeader").text(firstDesc);
					} else {
						// Remove the investment part and damage/percent part
						const cleanDesc = firstDesc
							.replace(/\d+ HP \/ \d+ \w+ /, "")
							.replace(/:\s*\d+-\d+ \(.*$/, "");
						$("#calcHeader").text(cleanDesc);
					}
				}

				renderResults();
			},
		});
	});
});
