#!/usr/bin/env python3
"""
Generate comparison chart for three municipalities as PNG.
"""
import matplotlib.pyplot as plt
import numpy as np

# Data from 2024 financial statements
municipalities = ['Lapua', 'Seinäjoki', 'Kauhava']
populations = [14_029, 66_610, 15_164]  # Asukasluvut 31.12.2024

# Values in original units (1000 € or days)
vuosikate_1000 = [7_502, 18_033, 9_552]  # 1000 €
lainakanta_1000 = [64_300, 368_324, 72_904]  # 1000 €
kassan_riittavyys_pv = [19, 8, 101]  # days

# Convert to millions (M) for readability
vuosikate_M = [v / 1000 for v in vuosikate_1000]
lainakanta_M = [v / 1000 for v in lainakanta_1000]

# Create figure with subplots
fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(16, 6))
fig.suptitle('Kuntavertailu 2024: Vuosikate, Lainakanta ja Kassan riittävyys', 
             fontsize=16, fontweight='bold')

# Chart 1: Vuosikate (M€)
bars1 = ax1.bar(municipalities, vuosikate_M, color=['#2E86AB', '#A23B72', '#F18F01'], alpha=0.8)
ax1.set_ylabel('Vuosikate (milj. €)', fontsize=12)
ax1.set_title('Vuosikate 2024', fontsize=13, fontweight='bold')
ax1.grid(axis='y', alpha=0.3, linestyle='--')
# Add value labels on bars
for i, (bar, val) in enumerate(zip(bars1, vuosikate_M)):
    height = bar.get_height()
    ax1.text(bar.get_x() + bar.get_width()/2., height,
             f'{val:.1f} M€\n({vuosikate_1000[i]:,} k€)',
             ha='center', va='bottom', fontsize=10)

# Chart 2: Lainakanta (M€)
bars2 = ax2.bar(municipalities, lainakanta_M, color=['#2E86AB', '#A23B72', '#F18F01'], alpha=0.8)
ax2.set_ylabel('Lainakanta 31.12.2024 (milj. €)', fontsize=12)
ax2.set_title('Lainakanta 31.12.2024', fontsize=13, fontweight='bold')
ax2.grid(axis='y', alpha=0.3, linestyle='--')
# Add value labels on bars
for i, (bar, val) in enumerate(zip(bars2, lainakanta_M)):
    height = bar.get_height()
    ax2.text(bar.get_x() + bar.get_width()/2., height,
             f'{val:.1f} M€\n({lainakanta_1000[i]:,} k€)',
             ha='center', va='bottom', fontsize=10)

# Chart 3: Kassan riittävyys (days)
bars3 = ax3.bar(municipalities, kassan_riittavyys_pv, color=['#2E86AB', '#A23B72', '#F18F01'], alpha=0.8)
ax3.set_ylabel('Kassan riittävyys (päivää)', fontsize=12)
ax3.set_title('Kassan riittävyys 2024', fontsize=13, fontweight='bold')
ax3.grid(axis='y', alpha=0.3, linestyle='--')
# Add value labels on bars
for i, (bar, val) in enumerate(zip(bars3, kassan_riittavyys_pv)):
    height = bar.get_height()
    ax3.text(bar.get_x() + bar.get_width()/2., height,
             f'{val} pv',
             ha='center', va='bottom', fontsize=11, fontweight='bold')

# Add population info as text below
pop_text = f'Asukasluvut 31.12.2024: Lapua {populations[0]:,}, Seinäjoki {populations[1]:,}, Kauhava {populations[2]:,}'
fig.text(0.5, 0.02, pop_text, ha='center', fontsize=10, style='italic')

plt.tight_layout(rect=[0, 0.05, 1, 0.98])
plt.savefig('Kunta-analyysi/kuntavertailu_2024.png', dpi=300, bbox_inches='tight')
print("Kaavio tallennettu: Kunta-analyysi/kuntavertailu_2024.png")

