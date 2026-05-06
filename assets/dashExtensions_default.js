window.dashExtensions = Object.assign({}, window.dashExtensions, {
    default: {
        function0: function(feature, context) {
            const {
                selected,
                low,
                high,
                mid
            } = context.hideout;
            const isSelected = selected.includes(feature.properties.neighborhood);
            const ratio = Math.min(Math.max(feature.properties.open_close_ratio || 1, low), high);

            let r, g, b;
            if (ratio < mid) {
                const t = (ratio - low) / (mid - low);
                r = 220;
                g = Math.round(220 * t);
                b = Math.round(220 * t);
            } else {
                const t = (ratio - mid) / (high - mid);
                r = Math.round(220 * (1 - t));
                g = Math.round(220 * (1 - t));
                b = 220;
            }

            return {
                fillColor: isSelected ? '#27ae60' : `rgb(${r},${g},${b})`,
                fillOpacity: 1,
                color: 'white',
                weight: 2,
                opacity: 1
            };
        }

    }
});