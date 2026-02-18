#!/usr/bin/env python3
"""
Apply compact registration pills to main.py
Run: python3 apply_compact_pills.py app/main.py
"""
import sys

if len(sys.argv) < 2:
    print("Usage: python3 apply_compact_pills.py app/main.py")
    sys.exit(1)

filepath = sys.argv[1]

with open(filepath, 'r') as f:
    content = f.read()

changes = 0

# ── Change 1a: Replace :class and :title on the registration span ──
old_class = """:class="reg.sport === 'Soccer' ? 'bg-green-50 text-green-700' : reg.sport === 'Basketball' ? 'bg-orange-50 text-orange-700' : reg.sport === 'Flag Football' ? 'bg-yellow-50 text-yellow-700' : reg.sport === 'Volleyball' ? 'bg-purple-50 text-purple-700' : 'bg-blue-50 text-blue-700'"
                                                      :title="reg.division">"""

new_class = """:class="sportColor(reg.sport)"
                                                      :title="reg.sport + ' \\u2013 ' + reg.season + ' (' + reg.division + ')'">"""

if old_class in content:
    content = content.replace(old_class, new_class)
    changes += 1
    print("✅ Change 1a: Updated :class and :title bindings")
else:
    print("⚠️  Change 1a: Could not find registration span :class/:title")

# ── Change 1b: Replace the inner spans (sport text + season text) ──
old_spans = """<span x-text="reg.sport"></span>
                                                    <span class="ml-1 opacity-60" x-text="reg.season"></span>"""

new_spans = """<span x-text="sportEmoji(reg.sport)"></span>
                                                    <span class="ml-0.5" x-text="shortSeason(reg.season)"></span>"""

if old_spans in content:
    content = content.replace(old_spans, new_spans)
    changes += 1
    print("✅ Change 1b: Updated pill content to emoji + abbreviated season")
else:
    print("⚠️  Change 1b: Could not find registration span inner content")

# ── Change 2: Add helper methods after rowClass ──
old_rowclass = """rowClass(player) {
                if (this.duplicateJerseys.has(player.id)) return 'bg-red-50 hover:bg-red-100';
                if (player.birthYear && this.birthYearColorMap[player.birthYear]) return 'bg-white hover:bg-gray-50';
                return 'bg-gray-50 hover:bg-gray-100';
            },"""

new_rowclass = """rowClass(player) {
                if (this.duplicateJerseys.has(player.id)) return 'bg-red-50 hover:bg-red-100';
                if (player.birthYear && this.birthYearColorMap[player.birthYear]) return 'bg-white hover:bg-gray-50';
                return 'bg-gray-50 hover:bg-gray-100';
            },
            
            sportEmoji(sport) {
                const map = { 'Soccer': '⚽', 'Basketball': '🏀', 'Flag Football': '🏈', 'Volleyball': '🏐', 'Baseball': '⚾', 'Softball': '🥎' };
                return map[sport] || '🏃';
            },
            
            shortSeason(season) {
                if (!season) return '';
                const abbrevs = { 'spring': 'Spr', 'summer': 'Sum', 'fall': 'Fall', 'winter': 'Win' };
                const parts = season.split(' ');
                if (parts.length === 2) {
                    const word = parts[0].toLowerCase();
                    const yr = parts[1].length === 4 ? "'" + parts[1].slice(2) : parts[1];
                    return (abbrevs[word] || parts[0]) + ' ' + yr;
                }
                return season;
            },
            
            sportColor(sport) {
                if (sport === 'Soccer') return 'bg-green-50 text-green-700';
                if (sport === 'Basketball') return 'bg-orange-50 text-orange-700';
                if (sport === 'Flag Football') return 'bg-yellow-50 text-yellow-700';
                if (sport === 'Volleyball') return 'bg-purple-50 text-purple-700';
                return 'bg-blue-50 text-blue-700';
            },"""

if old_rowclass in content:
    content = content.replace(old_rowclass, new_rowclass)
    changes += 1
    print("✅ Change 2: Added sportEmoji(), shortSeason(), sportColor() methods")
else:
    print("⚠️  Change 2: Could not find rowClass method")

# ── Write result ──
if changes > 0:
    with open(filepath, 'w') as f:
        f.write(content)
    print(f"\n🎉 Applied {changes} change(s) to {filepath}")
    print("\nRegistrations will now show as:")
    print("  ⚽ Fall '25  ⚽ Spr '26  🏀 2026  🏐 2025")
    print("  (hover for full details)")
else:
    print("\n❌ No changes applied — strings not found. Check main.py version.")
