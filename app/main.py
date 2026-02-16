import os
from datetime import datetime
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db, engine
from app.models import Base, Player, Registration
from app.api_routes import router as admin_api_router

Base.metadata.create_all(bind=engine)
app = FastAPI(title="POSA Jersey Management")
app.include_router(admin_api_router)

ADMIN_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>POSA Jersey Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
</head>
<body class="bg-gray-50" x-data="tableApp()" x-init="init()">
    <header class="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div class="max-w-7xl mx-auto px-4 py-4">
            <div class="flex items-center justify-between">
                <h1 class="text-2xl font-bold text-gray-900">POSA Jersey Admin</h1>
                <div class="flex items-center space-x-3">
                    <button @click="syncSportsEngine()" class="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg text-sm font-medium">Sync SportsEngine</button>
                </div>
            </div>
        </div>
    </header>

    <div class="bg-white border-b border-gray-200">
        <div class="max-w-7xl mx-auto px-4 py-4">
            <div class="flex flex-wrap gap-3 items-end">
                <div class="flex-1 min-w-64">
                    <label class="block text-xs font-medium text-gray-700 mb-1">Search</label>
                    <input type="search" x-model="filters.search" @input.debounce.300ms="applyFilters()" @keyup.enter="applyFilters()" placeholder="Name, email, or jersey #..." class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent">
                </div>
                <div class="w-32">
                    <label class="block text-xs font-medium text-gray-700 mb-1">Birth Year</label>
                    <select x-model="filters.birthYear" @change="applyFilters()" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500">
                        <option value="">All</option>
                        <template x-for="year in availableBirthYears" :key="year">
                            <option :value="year" x-text="year"></option>
                        </template>
                    </select>
                </div>
                <div class="w-40">
                    <label class="block text-xs font-medium text-gray-700 mb-1">Sport</label>
                    <select x-model="filters.sport" @change="applyFilters()" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500">
                        <option value="">All</option>
                        <template x-for="sport in availableSports" :key="sport">
                            <option :value="sport" x-text="sport"></option>
                        </template>
                    </select>
                </div>
                <div class="w-28">
                    <label class="block text-xs font-medium text-gray-700 mb-1">Year</label>
                    <select x-model="filters.year" @change="applyFilters()" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500">
                        <option value="">All</option>
                        <option value="2026">2026</option>
                        <option value="2025">2025</option>
                        <option value="2024">2024</option>
                    </select>
                </div>
                <div class="w-28">
                    <label class="block text-xs font-medium text-gray-700 mb-1">Season</label>
                    <select x-model="filters.season" @change="applyFilters()" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500">
                        <option value="">All</option>
                        <template x-for="season in availableSeasons" :key="season">
                            <option :value="season" x-text="season"></option>
                        </template>
                    </select>
                </div>
                <div class="w-40">
                    <label class="block text-xs font-medium text-gray-700 mb-1">Status</label>
                    <select x-model="filters.status" @change="applyFilters()" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500">
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
            <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
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
                    <tbody class="bg-white divide-y divide-gray-200">
                        <template x-for="player in filteredPlayers" :key="player.id">
                            <tr :class="rowClass(player)">
                                <td class="px-3 py-3">
                                    <div class="text-sm font-medium text-gray-900" x-text="player.name"></div>
                                    <div class="text-xs text-gray-500" x-text="'Born ' + (player.birthYear || '?')"></div>
                                </td>
                                <td class="px-3 py-3 text-center">
                                    <span class="px-2 py-0.5 text-sm font-semibold text-gray-700 bg-gray-100 rounded" x-text="'#' + (player.jersey || '-')"></span>
                                </td>
                                <td class="px-3 py-3"><div class="text-sm text-gray-600 truncate" x-text="player.email"></div></td>
                                <td class="px-3 py-3">
                                    <div class="flex flex-wrap gap-1">
                                        <template x-for="reg in player.registrations" :key="reg.id">
                                            <span class="inline-flex items-center px-1.5 py-0.5 text-xs rounded cursor-default"
                                                  :class="reg.sport === 'Soccer' ? 'bg-green-50 text-green-700' : reg.sport === 'Basketball' ? 'bg-orange-50 text-orange-700' : reg.sport === 'Flag Football' ? 'bg-yellow-50 text-yellow-700' : reg.sport === 'Volleyball' ? 'bg-purple-50 text-purple-700' : 'bg-blue-50 text-blue-700'"
                                                  :title="reg.division">
                                                <span x-text="reg.sport"></span>
                                                <span class="ml-1 opacity-60" x-text="(reg.season ? reg.season + ' ' : '') + reg.year"></span>
                                            </span>
                                        </template>
                                    </div>
                                </td>
                                <td class="px-3 py-3 text-center">
                                    <span x-show="!player.emailSent" class="px-2 py-0.5 text-xs font-medium bg-orange-100 text-orange-700 rounded">Needs Email</span>
                                    <span x-show="player.emailSent" class="px-2 py-0.5 text-xs font-medium bg-green-100 text-green-700 rounded">✓ Sent</span>
                                </td>
                                <td class="px-3 py-3 text-right">
                                    <div class="flex items-center justify-end space-x-1">
                                        <button @click="sendEmail(player)" class="p-1 rounded hover:bg-gray-100" :class="player.emailSent ? 'text-gray-400' : 'text-green-600'" :title="player.emailSent ? 'Resend Email' : 'Send Email'">
                                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path></svg>
                                        </button>
                                        <button @click="editPlayer(player)" class="p-1 rounded hover:bg-gray-100 text-blue-600" title="Edit">
                                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path></svg>
                                        </button>
                                    </div>
                                </td>
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
                        <label class="block text-sm font-medium text-gray-700 mb-1">Birth Year</label>
                        <input type="number" x-model="editingPlayer.birthYear" class="w-full px-3 py-2 border border-gray-300 rounded-lg">
                    </div>
                    <div class="mb-4">
                        <label class="block text-sm font-medium text-gray-700 mb-1">Email</label>
                        <input type="email" x-model="editingPlayer.email" class="w-full px-3 py-2 border border-gray-300 rounded-lg">
                    </div>
                    <div class="flex justify-end space-x-3">
                        <button @click="editingPlayer = null" class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50">Cancel</button>
                        <button @click="savePlayer()" class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">Save</button>
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
            availableSeasons: [],
            birthYearColorMap: {},
            duplicateJerseys: new Set(),
            
            async init() {
                await this.loadPlayers();
                this.loading = false;
            },
            
            async loadPlayers() {
                try {
                    const response = await fetch('/api/admin/players');
                    const data = await response.json();
                    this.allPlayers = data.players;
                    this.filteredPlayers = data.players;
                    this.availableBirthYears = [...new Set(data.players.map(p => p.birthYear).filter(Boolean))].sort((a, b) => b - a);
                    const allSports = new Set();
                    const allSeasons = new Set();
                    data.players.forEach(p => { p.registrations.forEach(r => { allSports.add(r.sport); if (r.season) allSeasons.add(r.season); }); });
                    this.availableSports = [...allSports].sort();
                    this.availableSeasons = [...allSeasons].sort();
                    this.buildRowMeta();
                } catch (error) {
                    console.error('Failed to load players:', error);
                }
            },
            
            applyFilters() {
                this.filteredPlayers = this.allPlayers.filter(player => {
                    if (this.filters.search) {
                        const search = this.filters.search.toLowerCase();
                        const matchesName = player.name.toLowerCase().includes(search);
                        const matchesEmail = player.email.toLowerCase().includes(search);
                        const matchesJersey = player.jersey ? player.jersey.toString().toLowerCase().includes(search) : false;
                        if (!matchesName && !matchesEmail && !matchesJersey) return false;
                    }
                    if (this.filters.birthYear && player.birthYear != this.filters.birthYear) return false;
                    if (this.filters.sport) {
                        const hasSport = player.registrations.some(r => r.sport === this.filters.sport);
                        if (!hasSport) return false;
                    }
                    if (this.filters.year) {
                        const hasYear = player.registrations.some(r => r.year == this.filters.year);
                        if (!hasYear) return false;
                    }
                    if (this.filters.season) {
                        const hasSeason = player.registrations.some(r => r.season === this.filters.season);
                        if (!hasSeason) return false;
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
                // Birth year alternating colors
                const years = [...new Set(this.filteredPlayers.map(p => p.birthYear).filter(Boolean))].sort((a, b) => b - a);
                this.birthYearColorMap = {};
                years.forEach((y, i) => { this.birthYearColorMap[y] = i % 2 === 0; });
                
                // Duplicate jersey detection within birth year
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
            },
            
            rowClass(player) {
                if (this.duplicateJerseys.has(player.id)) return 'bg-red-50 hover:bg-red-100';
                if (player.birthYear && this.birthYearColorMap[player.birthYear]) return 'bg-white hover:bg-gray-50';
                return 'bg-gray-50 hover:bg-gray-100';
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
                            birth_year: this.editingPlayer.birthYear
                        })
                    });
                    const data = await response.json();
                    if (data.success) {
                        await this.loadPlayers();
                        this.applyFilters();
                        this.editingPlayer = null;
                        alert('Player updated!');
                    }
                } catch (error) {
                    console.error('Failed to update player:', error);
                    alert('Failed to update player');
                }
            },
            
            async sendEmail(player) {
                try {
                    const response = await fetch(`/api/admin/players/${player.id}/send-email`, { method: 'POST' });
                    const data = await response.json();
                    if (data.success) {
                        alert(`Email sent to ${player.email}`);
                        // Reload players to update email status
                        await this.loadPlayers();
                        this.applyFilters();
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
    
    # Auto-assign jersey if needed
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
