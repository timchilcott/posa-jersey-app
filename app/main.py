import os
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.database import get_db, engine
from app.models import Base
from app.api_routes import router as admin_api_router

Base.metadata.create_all(bind=engine)
app = FastAPI(title="POSA Jersey Management")
app.include_router(admin_api_router)

# TEMPLATE EMBEDDED - NO EXTERNAL FILE
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
                    <button @click="syncSportsEngine()" class="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg text-sm font-medium">
                        Sync SportsEngine
                    </button>
                    <button @click="showAddPlayer = true" class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium">
                        + Add Player
                    </button>
                </div>
            </div>
        </div>
    </header>

    <div class="bg-white border-b border-gray-200">
        <div class="max-w-7xl mx-auto px-4 py-4">
            <div class="flex flex-wrap gap-3 items-end">
                
                <div class="flex-1 min-w-64">
                    <label class="block text-xs font-medium text-gray-700 mb-1">Search</label>
                    <input 
                        type="search" 
                        x-model="filters.search"
                        @input="applyFilters()"
                        placeholder="Name, email, or jersey #..."
                        class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    >
                </div>

                <div class="w-32">
                    <label class="block text-xs font-medium text-gray-700 mb-1">Birth Year</label>
                    <select 
                        x-model="filters.birthYear" 
                        @change="applyFilters()"
                        class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                    >
                        <option value="">All</option>
                        <template x-for="year in availableBirthYears" :key="year">
                            <option :value="year" x-text="year"></option>
                        </template>
                    </select>
                </div>

                <div class="w-40">
                    <label class="block text-xs font-medium text-gray-700 mb-1">Sport</label>
                    <select 
                        x-model="filters.sport" 
                        @change="applyFilters()"
                        class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                    >
                        <option value="">All</option>
                        <template x-for="sport in availableSports" :key="sport">
                            <option :value="sport" x-text="sport"></option>
                        </template>
                    </select>
                </div>

                <div class="w-28">
                    <label class="block text-xs font-medium text-gray-700 mb-1">Year</label>
                    <select 
                        x-model="filters.year" 
                        @change="applyFilters()"
                        class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                    >
                        <option value="">All</option>
                        <option value="2026">2026</option>
                        <option value="2025">2025</option>
                        <option value="2024">2024</option>
                    </select>
                </div>

                <div class="w-40">
                    <label class="block text-xs font-medium text-gray-700 mb-1">Status</label>
                    <select 
                        x-model="filters.status" 
                        @change="applyFilters()"
                        class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                    >
                        <option value="">All</option>
                        <option value="needsEmail">Needs Email</option>
                        <option value="waitingRoom">Waiting Room</option>
                        <option value="active">Active</option>
                    </select>
                </div>

                <button 
                    @click="clearFilters()" 
                    class="px-4 py-2 text-gray-600 hover:text-gray-900 text-sm font-medium"
                >
                    Clear
                </button>

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
                <table class="min-w-full divide-y divide-gray-200">
                    <thead class="bg-gray-50">
                        <tr>
                            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Birth Year</th>
                            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Jersey</th>
                            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Email</th>
                            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Registrations</th>
                            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                            <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                        </tr>
                    </thead>
                    <tbody class="bg-white divide-y divide-gray-200">
                        <template x-for="player in filteredPlayers" :key="player.id">
                            <tr class="hover:bg-gray-50">
                                <td class="px-4 py-4 whitespace-nowrap">
                                    <div class="text-sm font-medium text-gray-900" x-text="player.name"></div>
                                </td>
                                <td class="px-4 py-4 whitespace-nowrap">
                                    <div class="text-sm text-gray-900" x-text="player.birthYear"></div>
                                </td>
                                <td class="px-4 py-4 whitespace-nowrap">
                                    <span class="px-2 py-1 text-sm font-medium text-gray-700 bg-gray-100 rounded">#<span x-text="player.jersey"></span></span>
                                </td>
                                <td class="px-4 py-4 whitespace-nowrap">
                                    <div class="text-sm text-gray-600" x-text="player.email"></div>
                                </td>
                                <td class="px-4 py-4">
                                    <div class="flex flex-wrap gap-1">
                                        <template x-for="reg in player.registrations" :key="reg.id">
                                            <span class="inline-flex items-center px-2 py-1 text-xs bg-blue-50 text-blue-700 rounded">
                                                <span x-text="reg.sport"></span>
                                                <span class="ml-1 text-gray-500">•</span>
                                                <span class="ml-1" x-text="reg.division"></span>
                                                <span class="ml-1 text-gray-500">•</span>
                                                <span class="ml-1" x-text="reg.year"></span>
                                            </span>
                                        </template>
                                    </div>
                                </td>
                                <td class="px-4 py-4 whitespace-nowrap">
                                    <span x-show="!player.emailSent" class="px-2 py-1 text-xs font-medium bg-orange-100 text-orange-700 rounded">
                                        Needs Email
                                    </span>
                                    <span x-show="player.emailSent" class="px-2 py-1 text-xs font-medium bg-green-100 text-green-700 rounded">
                                        ✓ Email Sent
                                    </span>
                                </td>
                                <td class="px-4 py-4 whitespace-nowrap text-right text-sm font-medium">
                                    <div class="flex items-center justify-end space-x-2">
                                        <button @click="sendEmail(player)" x-show="!player.emailSent" class="text-green-600 hover:text-green-900" title="Send Email">
                                            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path>
                                            </svg>
                                        </button>
                                        <button @click="editPlayer(player)" class="text-blue-600 hover:text-blue-900" title="Edit">
                                            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                                            </svg>
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

    <script>
        function tableApp() {
            return {
                loading: true,
                showAddPlayer: false,
                allPlayers: [],
                filteredPlayers: [],
                filters: { search: '', birthYear: '', sport: '', year: '', status: '' },
                availableBirthYears: [],
                availableSports: [],
                
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
                        data.players.forEach(p => { p.registrations.forEach(r => allSports.add(r.sport)); });
                        this.availableSports = [...allSports].sort();
                    } catch (error) {
                        console.error('Failed to load players:', error);
                        alert('Failed to load players');
                    }
                },
                
                applyFilters() {
                    this.filteredPlayers = this.allPlayers.filter(player => {
                        if (this.filters.search) {
                            const search = this.filters.search.toLowerCase();
                            const matchesName = player.name.toLowerCase().includes(search);
                            const matchesEmail = player.email.toLowerCase().includes(search);
                            const matchesJersey = player.jersey.toString().includes(search);
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
                },
                
                clearFilters() {
                    this.filters = { search: '', birthYear: '', sport: '', year: '', status: '' };
                    this.applyFilters();
                },
                
                async sendEmail(player) {
                    try {
                        const response = await fetch(`/api/admin/players/${player.id}/send-email`, { method: 'POST' });
                        const data = await response.json();
                        if (data.success) {
                            player.emailSent = true;
                            alert(`Email sent to ${player.email}`);
                        }
                    } catch (error) {
                        console.error('Failed to send email:', error);
                        alert('Failed to send email');
                    }
                },
                
                editPlayer(player) {
                    console.log('Edit player:', player);
                },
                
                async syncSportsEngine() {
                    if (!confirm('Sync with SportsEngine? This may take a minute.')) return;
                    try {
                        const response = await fetch('/sync/pull', { method: 'POST' });
                        const data = await response.json();
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
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    return HTMLResponse(ADMIN_TEMPLATE)

@app.get("/health")
async def health():
    return {"status": "healthy"}
