import os
from datetime import datetime
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db, engine
from app.models import Base, Player, Registration
from app.api_routes import router as admin_api_router
from app.sync_routes import router as sync_router
from app.inventory_routes import router as inventory_router
from app.events_routes import router as events_router

Base.metadata.create_all(bind=engine)
app = FastAPI(title="POSA Jersey Management")
app.include_router(admin_api_router)
app.include_router(sync_router)
app.include_router(inventory_router)
app.include_router(events_router)

ADMIN_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>POSA Jersey</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
    tailwind.config = {
        theme: {
            extend: {
                colors: {
                    pines: { 50: '#f0f7f0', 100: '#d9edd9', 200: '#b3dbb3', 300: '#7fc07f', 400: '#5aa55a', 500: '#3C7939', 600: '#2f6130', 700: '#254d26', 800: '#1c3a1d', 900: '#142914' }
                }
            }
        }
    }
    </script>
    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
</head>
<body class="bg-gray-50" x-data="tableApp()" x-init="init()">
    <header class="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div class="max-w-7xl mx-auto px-4 py-3">
            <div class="flex items-center justify-between">
                <div class="flex items-center space-x-3">
                    <img src="https://cdn.prod.website-files.com/681d81085457ff1ea60182c2/684103edf65163765f534531_PINES_LOGO_DARK.svg" alt="Pines" class="h-8">
                </div>
                <div class="flex items-center space-x-3">
                    <a href="/admin/volunteers" class="text-pines-500 hover:text-pines-700 px-3 py-2 text-sm font-medium">Volunteers</a>
                    <a href="/inventory" class="text-pines-500 hover:text-pines-700 px-3 py-2 text-sm font-medium">Inventory</a>
                    <a href="/events" class="text-pines-500 hover:text-pines-700 px-3 py-2 text-sm font-medium">Events</a>
                    <button @click="syncSportsEngine()" class="bg-pines-500 hover:bg-pines-600 text-white px-4 py-2 rounded-lg text-sm font-medium">Sync SportsEngine</button>
                </div>
            </div>
        </div>
    </header>

    <div class="bg-white border-b border-gray-200">
        <div class="max-w-7xl mx-auto px-4 py-4">
            <div class="flex flex-wrap gap-3 items-end">
                <div class="flex-1 min-w-64">
                    <label class="block text-xs font-medium text-gray-700 mb-1">Search</label>
                    <input type="search" x-model="filters.search" @input.debounce.300ms="applyFilters()" @keyup.enter="applyFilters()" placeholder="Name, email, or jersey #..." class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-pines-500 focus:border-transparent">
                </div>
                <div class="w-32">
                    <label class="block text-xs font-medium text-gray-700 mb-1">Birth Year</label>
                    <select x-model="filters.birthYear" @change="applyFilters()" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-pines-500">
                        <option value="">All</option>
                        <template x-for="year in availableBirthYears" :key="year">
                            <option :value="year" x-text="year"></option>
                        </template>
                    </select>
                </div>
                <div class="w-40">
                    <label class="block text-xs font-medium text-gray-700 mb-1">Sport</label>
                    <select x-model="filters.sport" @change="applyFilters()" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-pines-500">
                        <option value="">All</option>
                        <template x-for="sport in availableSports" :key="sport">
                            <option :value="sport" x-text="sport"></option>
                        </template>
                    </select>
                </div>
                <div class="w-28">
                    <label class="block text-xs font-medium text-gray-700 mb-1">Year</label>
                    <select x-model="filters.year" @change="applyFilters()" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-pines-500">
                        <option value="">All</option>
                        <template x-for="y in availableYears" :key="y">
                            <option :value="y" x-text="y"></option>
                        </template>
                    </select>
                </div>
                <div class="w-28" x-show="availableSeasons.length > 0">
                    <label class="block text-xs font-medium text-gray-700 mb-1">Season</label>
                    <select x-model="filters.season" @change="applyFilters()" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-pines-500">
                        <option value="">All</option>
                        <template x-for="season in availableSeasons" :key="season">
                            <option :value="season" x-text="season"></option>
                        </template>
                    </select>
                </div>
                <div class="w-40">
                    <label class="block text-xs font-medium text-gray-700 mb-1">Status</label>
                    <select x-model="filters.status" @change="applyFilters()" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-pines-500">
                        <option value="">All</option>
                        <option value="needsEmail">Needs Email</option>
                        <option value="waitingRoom">Waiting Room</option>
                        <option value="active">Active</option>
                    </select>
                </div>
                <button @click="clearFilters()" class="px-4 py-2 text-gray-600 hover:text-gray-900 text-sm font-medium">Clear</button>
            </div>
            <div class="mt-3 text-sm text-gray-600">
                Showing <span class="font-medium" x-text="filteredPlayers.length"></span> of <span x-text="allPlayers.length"></span> players
            </div>
        </div>
    </div>

    <main class="max-w-7xl mx-auto px-4 py-6">
        <div x-show="loading" class="text-center py-12">
            <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-pines-500"></div>
            <p class="mt-2 text-gray-600">Loading players...</p>
        </div>

        <div x-show="!loading" class="bg-white rounded-lg shadow overflow-hidden">
            <div class="overflow-x-auto">
                <table class="min-w-full divide-y divide-gray-200 table-fixed">
                    <thead class="bg-gray-50">
                        <tr>
                            <th class="w-52 px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Player</th>
                            <th class="w-16 px-3 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">Jersey</th>
                            <th class="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Email</th>
                            <th class="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Registrations</th>
                            <th class="w-24 px-3 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                            <th class="w-20 px-3 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-200">
                        <template x-for="item in displayList" :key="item._key">
                            <tr :class="item._isHeader ? 'bg-pines-50 border-t-2 border-pines-200' : rowClass(item)">
                                <template x-if="item._isHeader">
                                    <td colspan="6" class="px-3 py-2">
                                        <span class="text-sm font-bold text-pines-700" x-text="'Birth Year ' + item.birthYear"></span>
                                        <span class="ml-2 text-xs text-pines-500" x-text="item._count + ' players'"></span>
                                    </td>
                                </template>
                                <template x-if="!item._isHeader">
                                    <td class="px-3 py-3">
                                        <div class="text-sm font-medium text-gray-900" x-text="item.name"></div>
                                    </td>
                                </template>
                                <template x-if="!item._isHeader">
                                    <td class="px-3 py-3 text-center">
                                        <span class="px-2 py-0.5 text-sm font-semibold text-gray-700 bg-gray-100 rounded" x-text="'#' + (item.jersey || '-')"></span>
                                    </td>
                                </template>
                                <template x-if="!item._isHeader">
                                    <td class="px-3 py-3"><div class="text-sm text-gray-600 truncate" x-text="item.email"></div></td>
                                </template>
                                <template x-if="!item._isHeader">
                                    <td class="px-3 py-3">
                                        <div class="flex flex-wrap gap-1">
                                            <template x-for="reg in sortedRegs(item.registrations)" :key="reg.id">
                                                <span class="inline-flex items-center px-1.5 py-0.5 text-xs rounded cursor-default"
                                                      :class="sportColor(reg.sport)"
                                                      :title="reg.sport + ' \u2013 ' + reg.season + ' (' + reg.division + ')'">
                                                    <span x-text="sportEmoji(reg.sport)"></span>
                                                    <span class="ml-0.5" x-text="shortSeason(reg.season)"></span>
                                                </span>
                                            </template>
                                        </div>
                                    </td>
                                </template>
                                <template x-if="!item._isHeader">
                                    <td class="px-3 py-3 text-center">
                                        <span x-show="!item.emailSent" class="px-2 py-0.5 text-xs font-medium bg-orange-100 text-orange-700 rounded">Needs Email</span>
                                        <span x-show="item.emailSent" class="px-2 py-0.5 text-xs font-medium bg-green-100 text-green-700 rounded">✓ Sent</span>
                                    </td>
                                </template>
                                <template x-if="!item._isHeader">
                                    <td class="px-3 py-3 text-right">
                                        <div class="flex items-center justify-end space-x-1">
                                            <button @click="sendEmail(item)" class="p-1 rounded hover:bg-gray-100" :class="item.emailSent ? 'text-gray-400' : 'text-green-600'" :title="item.emailSent ? 'Resend Email' : 'Send Email'">
                                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path></svg>
                                            </button>
                                            <button @click="editPlayer(item)" class="p-1 rounded hover:bg-gray-100 text-pines-500" title="Edit">
                                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path></svg>
                                            </button>
                                            <button @click="markVolunteer(item)" class="p-1 rounded hover:bg-purple-100 text-purple-500" title="Mark as Volunteer">
                                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path></svg>
                                            </button>
                                        </div>
                                    </td>
                                </template>
                            </tr>
                        </template>
                    </tbody>
                </table>
            </div>
            <div x-show="filteredPlayers.length === 0 && !loading" class="text-center py-12">
                <div class="text-gray-400 text-5xl mb-3">🔍</div>
                <h3 class="text-lg font-medium text-gray-900 mb-1">No players found</h3>
                <p class="text-gray-500">Try adjusting your filters</p>
            </div>
        </div>
    </main>

    <div x-show="editingPlayer" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4" @click.self="editingPlayer = null">
        <div class="bg-white rounded-lg p-6 max-w-md w-full">
            <h3 class="text-xl font-bold mb-4">Edit Player</h3>
            <template x-if="editingPlayer">
                <div>
                    <div class="mb-4">
                        <label class="block text-sm font-medium text-gray-700 mb-1">Name</label>
                        <input type="text" x-model="editingPlayer.name" class="w-full px-3 py-2 border border-gray-300 rounded-lg">
                    </div>
                    <div class="mb-4">
                        <label class="block text-sm font-medium text-gray-700 mb-1">Jersey Number</label>
                        <input type="number" x-model="editingPlayer.jersey" class="w-full px-3 py-2 border border-gray-300 rounded-lg">
                    </div>
                    <div class="mb-4">
                        <label class="block text-sm font-medium text-gray-700 mb-1">Birth Year</label>
                        <input type="number" x-model="editingPlayer.birthYear" class="w-full px-3 py-2 border border-gray-300 rounded-lg">
                    </div>
                    <div class="mb-4">
                        <label class="block text-sm font-medium text-gray-700 mb-1">Email</label>
                        <input type="email" x-model="editingPlayer.email" class="w-full px-3 py-2 border border-gray-300 rounded-lg">
                    </div>
                    <div class="flex justify-end space-x-3">
                        <button @click="editingPlayer = null" class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50">Cancel</button>
                        <button @click="savePlayer()" class="px-4 py-2 bg-pines-500 text-white rounded-lg hover:bg-pines-600">Save</button>
                    </div>
                </div>
            </template>
        </div>
    </div>

    <script>
    function tableApp() {
        return {
            loading: true,
            editingPlayer: null,
            allPlayers: [],
            filteredPlayers: [],
            filters: { search: '', birthYear: '', sport: '', year: '', season: '', status: '' },
            availableBirthYears: [],
            availableSports: [],
            availableYears: [],
            availableSeasons: [],
            birthYearColorMap: {},
            duplicateJerseys: new Set(),
            displayList: [],
            
            async init() {
                await this.loadPlayers();
                this.loading = false;
            },
            
            async loadPlayers() {
                try {
                    const response = await fetch('/api/admin/players');
                    const data = await response.json();
                    this.allPlayers = data.players;
                    this.applyFilters();
                } catch (error) {
                    console.error('Failed to load players:', error);
                }
            },
            
            getSeasonYear(season) {
                if (!season) return '';
                const match = season.match(/\d{4}/);
                return match ? match[0] : '';
            },
            
            updateAvailableOptions() {
                const playerFiltered = this.allPlayers.filter(p => {
                    if (this.filters.search) {
                        const s = this.filters.search.toLowerCase();
                        if (!p.name.toLowerCase().includes(s) && !p.email.toLowerCase().includes(s) && !(p.jersey && p.jersey.toString().includes(s))) return false;
                    }
                    if (this.filters.status === 'needsEmail' && p.emailSent) return false;
                    if (this.filters.status === 'waitingRoom' && !p.registrations.some(r => r.division === 'Waiting Room')) return false;
                    if (this.filters.status === 'active' && !p.registrations.some(r => r.year === 2026)) return false;
                    return true;
                });
                
                const allRegs = [];
                playerFiltered.forEach(p => {
                    p.registrations.forEach(r => {
                        allRegs.push({ sport: r.sport, year: r.year, season: r.season, seasonYear: this.getSeasonYear(r.season), birthYear: p.birthYear });
                    });
                });
                
                const matchExcept = (regs, exclude) => regs.filter(r => {
                    if (exclude !== 'sport' && this.filters.sport && r.sport !== this.filters.sport) return false;
                    if (exclude !== 'year' && this.filters.year && String(r.year) !== String(this.filters.year)) return false;
                    if (exclude !== 'season' && this.filters.season && r.season !== this.filters.season) return false;
                    if (exclude !== 'birthYear' && this.filters.birthYear && String(r.birthYear) !== String(this.filters.birthYear)) return false;
                    return true;
                });
                
                this.availableSports = [...new Set(matchExcept(allRegs, 'sport').map(r => r.sport).filter(Boolean))].filter(s => s.toLowerCase() !== 'unknown').sort();
                this.availableYears = [...new Set(matchExcept(allRegs, 'year').map(r => r.year).filter(Boolean))].sort((a, b) => b - a);
                this.availableSeasons = [...new Set(matchExcept(allRegs, 'season').map(r => r.season).filter(Boolean))].filter(s => s.toLowerCase() !== 'unknown' && /[a-z]/i.test(s)).sort();
                this.availableBirthYears = [...new Set(matchExcept(allRegs, 'birthYear').map(r => r.birthYear).filter(Boolean))].sort((a, b) => b - a);
                
                if (this.filters.sport && !this.availableSports.includes(this.filters.sport)) this.filters.sport = '';
                if (this.filters.year && !this.availableYears.map(String).includes(String(this.filters.year))) this.filters.year = '';
                if (this.filters.season && !this.availableSeasons.includes(this.filters.season)) this.filters.season = '';
                if (this.filters.birthYear && !this.availableBirthYears.map(String).includes(String(this.filters.birthYear))) this.filters.birthYear = '';
            },
            
            applyFilters() {
                this.updateAvailableOptions();
                
                this.filteredPlayers = this.allPlayers.filter(player => {
                    if (this.filters.search) {
                        const search = this.filters.search.toLowerCase();
                        const matchesName = player.name.toLowerCase().includes(search);
                        const matchesEmail = player.email.toLowerCase().includes(search);
                        const matchesJersey = player.jersey ? player.jersey.toString().toLowerCase().includes(search) : false;
                        if (!matchesName && !matchesEmail && !matchesJersey) return false;
                    }
                    if (this.filters.birthYear && player.birthYear != this.filters.birthYear) return false;
                    // Combined registration filter: sport + year + season must match the SAME registration
                    if (this.filters.sport || this.filters.year || this.filters.season) {
                        const matchingReg = player.registrations.some(r => {
                            if (this.filters.sport && r.sport !== this.filters.sport) return false;
                            if (this.filters.year && r.year != this.filters.year) return false;
                            if (this.filters.season && r.season !== this.filters.season) return false;
                            return true;
                        });
                        if (!matchingReg) return false;
                    }
                    
                    if (this.filters.status === 'needsEmail' && player.emailSent) return false;
                    if (this.filters.status === 'waitingRoom') {
                        const inWaitingRoom = player.registrations.some(r => r.division === 'Waiting Room');
                        if (!inWaitingRoom) return false;
                    }
                    if (this.filters.status === 'active') {
                        const hasActive = player.registrations.some(r => r.year === 2026);
                        if (!hasActive) return false;
                    }
                    return true;
                });
                this.buildRowMeta();
            },
            
            buildRowMeta() {
                const years = [...new Set(this.filteredPlayers.map(p => p.birthYear).filter(Boolean))].sort((a, b) => b - a);
                this.birthYearColorMap = {};
                years.forEach((y, i) => { this.birthYearColorMap[y] = i % 2 === 0; });
                
                this.duplicateJerseys = new Set();
                const byYear = {};
                this.filteredPlayers.forEach(p => {
                    if (p.birthYear && p.jersey) {
                        const key = p.birthYear + '-' + p.jersey;
                        if (byYear[key]) {
                            this.duplicateJerseys.add(byYear[key]);
                            this.duplicateJerseys.add(p.id);
                        } else {
                            byYear[key] = p.id;
                        }
                    }
                });
                
                this.displayList = [];
                let lastYear = null;
                const yearCounts = {};
                this.filteredPlayers.forEach(p => {
                    yearCounts[p.birthYear] = (yearCounts[p.birthYear] || 0) + 1;
                });
                this.filteredPlayers.forEach(p => {
                    if (p.birthYear !== lastYear) {
                        this.displayList.push({ _isHeader: true, _key: 'h-' + (p.birthYear || 'none'), birthYear: p.birthYear || 'Unknown', _count: yearCounts[p.birthYear] || 0 });
                        lastYear = p.birthYear;
                    }
                    this.displayList.push({ ...p, _isHeader: false, _key: 'p-' + p.id });
                });
            },
            
            rowClass(player) {
                if (this.duplicateJerseys.has(player.id)) return 'bg-red-50 hover:bg-red-100';
                return 'bg-white hover:bg-gray-50';
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
            },
            
            sortedRegs(regs) {
                // Sort newest first. Within same year, named seasons sort by
                // calendar position: spring(5) > summer(4) > [no keyword](3) > fall(2) > winter(1)
                const seasonOrder = { 'spring': 5, 'summer': 4, 'fall': 2, 'winter': 1 };
                return [...regs].sort((a, b) => {
                    const yearA = parseInt((a.season || '').match(/\d{4}/)?.[0] || a.year || 0);
                    const yearB = parseInt((b.season || '').match(/\d{4}/)?.[0] || b.year || 0);
                    if (yearB !== yearA) return yearB - yearA;
                    const wordA = (a.season || '').split(' ')[0].toLowerCase();
                    const wordB = (b.season || '').split(' ')[0].toLowerCase();
                    return (seasonOrder[wordB] || 3) - (seasonOrder[wordA] || 3);
                });
            },
            
            clearFilters() {
                this.filters = { search: '', birthYear: '', sport: '', year: '', season: '', status: '' };
                this.applyFilters();
            },
            
            editPlayer(player) {
                this.editingPlayer = { 
                    ...player
                };
            },
            
            async savePlayer() {
                try {
                    const response = await fetch(`/api/players/${this.editingPlayer.id}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            full_name: this.editingPlayer.name,
                            parent_email: this.editingPlayer.email,
                            birth_year: this.editingPlayer.birthYear,
                            jersey_number: this.editingPlayer.jersey
                        })
                    });
                    const data = await response.json();
                    if (data.success) {
                        await this.loadPlayers();
                        this.editingPlayer = null;
                        alert('Player updated!');
                    }
                } catch (error) {
                    console.error('Failed to update player:', error);
                    alert('Failed to update player');
                }
            },
            
            async markVolunteer(player) {
                if (!confirm(`Mark ${player.name} as a volunteer? They will be moved to the Volunteers page.`)) return;
                try {
                    const response = await fetch(`/api/players/${player.id}/set-volunteer`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ is_volunteer: true })
                    });
                    const data = await response.json();
                    if (data.success) {
                        await this.loadPlayers();
                    } else {
                        alert('Failed: ' + (data.error || 'Unknown error'));
                    }
                } catch (error) {
                    console.error('Failed to mark volunteer:', error);
                    alert('Failed to mark as volunteer');
                }
            },
            
            async sendEmail(player) {
                try {
                    const response = await fetch(`/api/admin/players/${player.id}/send-email`, { method: 'POST' });
                    const data = await response.json();
                    if (data.success) {
                        alert(`Email sent to ${player.email}`);
                        await this.loadPlayers();
                    } else {
                        alert(`Failed: ${data.message || data.error}`);
                    }
                } catch (error) {
                    console.error('Failed to send email:', error);
                    alert('Failed to send email');
                }
            },
            
            async syncSportsEngine() {
                if (!confirm('Sync with SportsEngine?')) return;
                try {
                    const response = await fetch('/sync/pull', { method: 'POST' });
                    await response.json();
                    alert('Sync complete!');
                    await this.loadPlayers();
                } catch (error) {
                    console.error('Sync failed:', error);
                    alert('Sync failed');
                }
            }
        }
    }
    </script>
</body>
</html>"""

@app.get("/")
async def home():
    return {"status": "ok"}

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    return HTMLResponse(ADMIN_TEMPLATE)

VOLUNTEER_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>POSA Volunteers</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
    tailwind.config = {
        theme: {
            extend: {
                colors: {
                    pines: { 50: '#f0f7f0', 100: '#d9edd9', 200: '#b3dbb3', 300: '#7fc07f', 400: '#5aa55a', 500: '#3C7939', 600: '#2f6130', 700: '#254d26', 800: '#1c3a1d', 900: '#142914' }
                }
            }
        }
    }
    </script>
    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
</head>
<body class="bg-gray-50" x-data="volunteerApp()" x-init="init()">
    <header class="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div class="max-w-7xl mx-auto px-4 py-3">
            <div class="flex items-center justify-between">
                <div class="flex items-center space-x-3">
                    <img src="https://cdn.prod.website-files.com/681d81085457ff1ea60182c2/684103edf65163765f534531_PINES_LOGO_DARK.svg" alt="Pines" class="h-8">
                    <h1 class="text-xl font-bold text-gray-900">Volunteers</h1>
                </div>
                <div class="flex items-center space-x-3">
                    <a href="/admin" class="text-pines-500 hover:text-pines-700 px-3 py-2 text-sm font-medium">&larr; Players</a>
                    <a href="/inventory" class="text-pines-500 hover:text-pines-700 px-3 py-2 text-sm font-medium">Inventory</a>
                    <a href="/events" class="text-pines-500 hover:text-pines-700 px-3 py-2 text-sm font-medium">Events</a>
                </div>
            </div>
        </div>
    </header>

    <div class="bg-white border-b border-gray-200">
        <div class="max-w-7xl mx-auto px-4 py-4">
            <div class="flex flex-wrap gap-3 items-end">
                <div class="flex-1 min-w-64">
                    <label class="block text-xs font-medium text-gray-700 mb-1">Search</label>
                    <input type="search" x-model="search" @input.debounce.300ms="applyFilter()" placeholder="Name or email..." class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-pines-500 focus:border-transparent">
                </div>
                <div class="w-48">
                    <label class="block text-xs font-medium text-gray-700 mb-1">Type</label>
                    <select x-model="typeFilter" @change="applyFilter()" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-pines-500">
                        <option value="">All</option>
                        <template x-for="t in availableTypes" :key="t">
                            <option :value="t" x-text="t"></option>
                        </template>
                    </select>
                </div>
                <button @click="search = ''; typeFilter = ''; applyFilter()" class="px-4 py-2 text-gray-600 hover:text-gray-900 text-sm font-medium">Clear</button>
            </div>
            <div class="mt-3 text-sm text-gray-600">
                Showing <span class="font-medium" x-text="filtered.length"></span> of <span x-text="all.length"></span> volunteers
            </div>
        </div>
    </div>

    <main class="max-w-7xl mx-auto px-4 py-6">
        <div x-show="loading" class="text-center py-12">
            <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-pines-500"></div>
            <p class="mt-2 text-gray-600">Loading volunteers...</p>
        </div>

        <div x-show="!loading" class="bg-white rounded-lg shadow overflow-hidden">
            <div class="overflow-x-auto">
                <table class="min-w-full divide-y divide-gray-200 table-fixed">
                    <thead class="bg-gray-50">
                        <tr>
                            <th class="w-56 px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                            <th class="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Email</th>
                            <th class="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Registration Type</th>
                            <th class="w-24 px-3 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                            <th class="w-20 px-3 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                        </tr>
                    </thead>
                    <tbody class="bg-white divide-y divide-gray-200">
                        <template x-for="vol in filtered" :key="vol.id">
                            <tr class="hover:bg-gray-50">
                                <td class="px-3 py-3">
                                    <div class="text-sm font-medium text-gray-900" x-text="vol.name"></div>
                                </td>
                                <td class="px-3 py-3"><div class="text-sm text-gray-600" x-text="vol.email"></div></td>
                                <td class="px-3 py-3">
                                    <div class="flex flex-wrap gap-1">
                                        <template x-for="reg in vol.registrations" :key="reg.id">
                                            <span class="inline-flex items-center px-1.5 py-0.5 text-xs rounded bg-pines-50 text-pines-700" x-text="reg.division"></span>
                                        </template>
                                    </div>
                                </td>
                                <td class="px-3 py-3 text-center">
                                    <span x-show="!vol.emailSent" class="px-2 py-0.5 text-xs font-medium bg-orange-100 text-orange-700 rounded">Needs Email</span>
                                    <span x-show="vol.emailSent" class="px-2 py-0.5 text-xs font-medium bg-green-100 text-green-700 rounded">✓ Sent</span>
                                </td>
                                <td class="px-3 py-3 text-right">
                                    <button @click="moveToPlayers(vol)" class="p-1 rounded hover:bg-pines-100 text-pines-500" title="Move to Players">
                                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z"></path></svg>
                                    </button>
                                </td>
                            </tr>
                        </template>
                    </tbody>
                </table>
            </div>
            <div x-show="filtered.length === 0 && !loading" class="text-center py-12">
                <div class="text-gray-400 text-5xl mb-3">🙋</div>
                <h3 class="text-lg font-medium text-gray-900 mb-1">No volunteers found</h3>
                <p class="text-gray-500">Try adjusting your filters</p>
            </div>
        </div>
    </main>

    <script>
    function volunteerApp() {
        return {
            loading: true,
            all: [],
            filtered: [],
            search: '',
            typeFilter: '',
            availableTypes: [],
            
            async init() {
                try {
                    const response = await fetch('/api/admin/players?volunteers_only=true');
                    const data = await response.json();
                    this.all = data.players;
                    this.filtered = data.players;
                    const types = new Set();
                    data.players.forEach(v => v.registrations.forEach(r => types.add(r.division)));
                    this.availableTypes = [...types].sort();
                } catch (error) {
                    console.error('Failed to load volunteers:', error);
                }
                this.loading = false;
            },
            
            applyFilter() {
                this.filtered = this.all.filter(vol => {
                    if (this.search) {
                        const s = this.search.toLowerCase();
                        if (!vol.name.toLowerCase().includes(s) && !vol.email.toLowerCase().includes(s)) return false;
                    }
                    if (this.typeFilter) {
                        if (!vol.registrations.some(r => r.division === this.typeFilter)) return false;
                    }
                    return true;
                });
            },
            
            async moveToPlayers(vol) {
                if (!confirm(`Move ${vol.name} to the Players list?`)) return;
                try {
                    const response = await fetch(`/api/players/${vol.id}/set-volunteer`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ is_volunteer: false })
                    });
                    const data = await response.json();
                    if (data.success) {
                        this.all = this.all.filter(v => v.id !== vol.id);
                        this.applyFilter();
                    } else {
                        alert('Failed: ' + (data.error || 'Unknown error'));
                    }
                } catch (error) {
                    console.error('Failed:', error);
                    alert('Failed to move to players');
                }
            }
        }
    }
    </script>
</body>
</html>"""

@app.get("/admin/volunteers", response_class=HTMLResponse)
async def admin_volunteers(request: Request):
    return HTMLResponse(VOLUNTEER_TEMPLATE)

@app.get("/inventory", response_class=HTMLResponse)
async def inventory_page():
    import pathlib
    html_path = pathlib.Path(__file__).parent / "templates" / "inventory_page.html"
    with open(html_path, "r") as f:
        return HTMLResponse(f.read())

@app.get("/events", response_class=HTMLResponse)
async def events_page():
    import pathlib
    html_path = pathlib.Path(__file__).parent / "templates" / "events_page.html"
    with open(html_path, "r") as f:
        return HTMLResponse(f.read())

@app.post("/api/players/{player_id}/set-volunteer")
async def set_volunteer(player_id: int, request: Request, db: Session = Depends(get_db)):
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        return {"success": False, "error": "Player not found"}
    
    data = await request.json()
    player.locked = bool(data.get("is_volunteer", False))
    db.commit()
    
    return {"success": True, "is_volunteer": player.locked}

@app.put("/api/players/{player_id}")
async def update_player(player_id: int, request: Request, db: Session = Depends(get_db)):
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        return {"success": False, "error": "Player not found"}
    
    data = await request.json()
    
    if "full_name" in data:
        player.full_name = data["full_name"]
    if "parent_email" in data:
        player.parent_email = data["parent_email"]
    if "birth_year" in data:
        player.birth_year = data["birth_year"]
    if "jersey_number" in data and data["jersey_number"] is not None:
        player.jersey_number = int(data["jersey_number"])
    
    if "birth_year" in data and data["birth_year"]:
        if not player.jersey_number or player.jersey_number == 0:
            max_jersey = db.query(func.max(Player.jersey_number)).filter(
                Player.birth_year == data["birth_year"]
            ).scalar()
            
            try:
                next_num = int(max_jersey or 0) + 1
            except:
                next_num = 1
            
            player.jersey_number = next_num
    
    db.commit()
    
    return {
        "success": True, 
        "jersey": player.jersey_number
    }

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/api/debug/seasons", response_class=HTMLResponse)
async def debug_seasons(db: Session = Depends(get_db)):
    """Show all distinct season values and counts"""
    from sqlalchemy import text
    rows = db.execute(text("""
        SELECT season, sport, 
               EXTRACT(YEAR FROM created_at)::int as reg_year,
               COUNT(*) as cnt
        FROM registrations 
        GROUP BY season, sport, reg_year
        ORDER BY reg_year DESC, sport, season
    """)).fetchall()
    
    lines = ["<h2>Season Values in Database</h2><table border='1' cellpadding='5'>"]
    lines.append("<tr><th>Season</th><th>Sport</th><th>Reg Year</th><th>Count</th></tr>")
    for row in rows:
        season_val = repr(row[0])
        lines.append(f"<tr><td>{season_val}</td><td>{row[1]}</td><td>{row[2]}</td><td>{row[3]}</td></tr>")
    lines.append("</table>")
    
    return f"<html><body style='font-family: monospace; padding: 20px;'>{''.join(lines)}</body></html>"

@app.get("/api/debug/divisions", response_class=HTMLResponse)
async def debug_divisions(db: Session = Depends(get_db)):
    """Show all distinct division values"""
    from sqlalchemy import text
    rows = db.execute(text("""
        SELECT division, sport, COUNT(*) as cnt
        FROM registrations 
        GROUP BY division, sport
        ORDER BY sport, division
    """)).fetchall()
    
    lines = ["<h2>Division Values in Database</h2><table border='1' cellpadding='5'>"]
    lines.append("<tr><th>Division</th><th>Sport</th><th>Count</th></tr>")
    for row in rows:
        lines.append(f"<tr><td>{row[0]}</td><td>{row[1]}</td><td>{row[2]}</td></tr>")
    lines.append("</table>")
    
    return f"<html><body style='font-family: monospace; padding: 20px;'>{''.join(lines)}</body></html>"


@app.get("/api/cleanup-registrations", response_class=HTMLResponse)
async def cleanup_registrations(db: Session = Depends(get_db)):
    """One-time fix: clean up bad registration data. DELETE AFTER USE."""
    from sqlalchemy import text
    
    fixes = [
        ("UPDATE registrations SET season = 'Spring 2026' WHERE LOWER(sport) = 'soccer' AND TRIM(season) = '2026'", "soccer '2026' → 'Spring 2026'"),
    ]
    
    results = []
    for sql, label in fixes:
        count = db.execute(text(sql)).rowcount
        results.append(f"{label}: {count} rows affected")
    
    db.commit()
    
    detail = "<br>".join(results)
    return f"""<html><body style='font-family: monospace; padding: 20px;'>
        <h2>Registration Cleanup Complete</h2>
        <p>{detail}</p>
        <hr>
        <p><a href='/api/debug/seasons'>View current season values</a></p>
        <p><a href='/api/debug/divisions'>View current divisions</a></p>
        <p style='color: red; font-weight: bold;'>DELETE THIS ENDPOINT AFTER CONFIRMING!</p>
    </body></html>"""
