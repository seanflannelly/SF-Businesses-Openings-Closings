window.dashExtensions = Object.assign({}, window.dashExtensions, {
    default: {
        function0: function(feature, context) {
            const {
                selected,
                low,
                high
            } = context.hideout;
            const isSelected = selected.includes(feature.properties.neighborhood);
            const ratio = feature.properties.open_close_ratio || 1;

            const norm = Math.min(Math.max((ratio - low) / (high - low), 0), 1);

            let r, g, b;
            if (norm < 0.5) {
                const t = norm / 0.5;
                r = Math.round(180 + (240 - 180) * t);
                g = Math.round(30 + (240 - 30) * t);
                b = Math.round(30 + (240 - 30) * t);
            } else {
                const t = (norm - 0.5) / 0.5;
                r = Math.round(240 + (30 - 240) * t);
                g = Math.round(240 + (100 - 240) * t);
                b = Math.round(240 + (180 - 240) * t);
            }

            return {
                fillColor: isSelected ? '#58d68d' : `rgb(${r},${g},${b})`,
                fillOpacity: isSelected ? 0.9 : 0.85,
                color: 'white',
                weight: 1
            };
        }

    }
});