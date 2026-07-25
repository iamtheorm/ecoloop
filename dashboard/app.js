/**
 * app.js — Dashboard logic for Eco-Loop Building Agent
 * Loads simulation data and renders interactive charts and metrics.
 */

// Chart.js default config
Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.05)';
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.font.size = 11;

// Global state
let reportData = null;

// ===== DATA LOADING =====
async function loadData() {
    try {
        const response = await fetch('data.json');
        if (!response.ok) throw new Error('No data.json found');
        reportData = await response.json();
        renderDashboard(reportData);
    } catch (e) {
        console.warn('No live data found, loading demo data...');
        reportData = generateDemoData();
        renderDashboard(reportData);
    }
}

// ===== RENDER DASHBOARD =====
function renderDashboard(data) {
    renderHeroMetrics(data.summary);
    renderEnergyChart(data);
    renderTemperatureChart(data);
    renderPMVChart(data);
    renderSetpointChart(data);
    renderBreakdownChart(data);
    renderDecisionLog(data.agent_decisions || []);
}

// ===== HERO METRICS =====
function renderHeroMetrics(summary) {
    animateValue('energy-saved', 0, summary.energy_savings_kwh, 2000, 1);
    animateValue('savings-pct', 0, summary.energy_savings_percent, 2000, 1, '%');
    animateValue('cost-savings', 0, summary.estimated_cost_savings_usd, 2000, 2, '', '$');
    
    // Comfort score
    const totalTimesteps = (summary.optimized_comfort_violations || 0) + 100;
    const comfortPct = Math.max(0, Math.min(100, 
        100 - (summary.optimized_comfort_violations / totalTimesteps * 100)
    )).toFixed(1);
    animateValue('comfort-score', 0, parseFloat(comfortPct), 2000, 1, '%');
    
    // Savings bar
    setTimeout(() => {
        const bar = document.getElementById('savings-bar');
        bar.style.width = Math.min(100, Math.max(5, summary.energy_savings_percent)) + '%';
    }, 500);
    
    // Decision count
    document.getElementById('decision-count').textContent = 
        `${summary.total_agent_decisions || 0} decisions`;
}

function animateValue(elementId, start, end, duration, decimals = 0, suffix = '', prefix = '') {
    const element = document.getElementById(elementId);
    if (!element) return;
    
    const startTime = performance.now();
    
    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        
        // Ease out cubic
        const eased = 1 - Math.pow(1 - progress, 3);
        const current = start + (end - start) * eased;
        
        element.textContent = prefix + current.toFixed(decimals) + suffix;
        
        if (progress < 1) {
            requestAnimationFrame(update);
        }
    }
    
    requestAnimationFrame(update);
}

// ===== ENERGY COMPARISON CHART =====
function renderEnergyChart(data) {
    const ctx = document.getElementById('energyChart').getContext('2d');
    
    // Aggregate by hour
    const baselineByHour = aggregateByHour(data.baseline_timeseries, 'total_energy_kwh');
    const optimizedByHour = aggregateByHour(data.optimized_timeseries, 'total_energy_kwh');
    
    const labels = Object.keys(baselineByHour).map(h => `${h}:00`);
    
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Baseline (kWh)',
                    data: Object.values(baselineByHour),
                    borderColor: '#ef4444',
                    backgroundColor: 'rgba(239, 68, 68, 0.1)',
                    fill: true,
                    tension: 0.4,
                    borderWidth: 2,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                },
                {
                    label: 'AI-Optimized (kWh)',
                    data: Object.values(optimizedByHour),
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    fill: true,
                    tension: 0.4,
                    borderWidth: 2,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { intersect: false, mode: 'index' },
            plugins: {
                legend: { position: 'top', align: 'end' },
                tooltip: {
                    backgroundColor: 'rgba(17, 24, 39, 0.95)',
                    titleColor: '#f1f5f9',
                    bodyColor: '#94a3b8',
                    borderColor: 'rgba(99, 102, 241, 0.3)',
                    borderWidth: 1,
                    padding: 12,
                    cornerRadius: 8,
                }
            },
            scales: {
                y: { 
                    title: { display: true, text: 'Energy (kWh)' },
                    grid: { color: 'rgba(255,255,255,0.03)' }
                },
                x: { grid: { display: false } }
            }
        }
    });
}

// ===== TEMPERATURE CHART =====
function renderTemperatureChart(data) {
    const ctx = document.getElementById('tempChart').getContext('2d');
    
    const zones = getUniqueZones(data.optimized_timeseries);
    const colors = ['#6366f1', '#8b5cf6', '#a78bfa', '#10b981', '#3b82f6'];
    
    const datasets = zones.slice(0, 5).map((zone, i) => {
        const zoneData = data.optimized_timeseries
            .filter(r => r.zone_name === zone)
            .map(r => ({ x: r.sim_time_hours, y: r.zone_temp_c }));
        
        return {
            label: zone,
            data: zoneData,
            borderColor: colors[i],
            backgroundColor: 'transparent',
            tension: 0.3,
            borderWidth: 1.5,
            pointRadius: 0,
        };
    });
    
    new Chart(ctx, {
        type: 'line',
        data: { datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'top', align: 'end' } },
            scales: {
                x: { type: 'linear', title: { display: true, text: 'Simulation Hours' }, grid: { display: false } },
                y: { title: { display: true, text: 'Temperature (°C)' }, grid: { color: 'rgba(255,255,255,0.03)' } }
            }
        }
    });
}

// ===== PMV COMFORT CHART =====
function renderPMVChart(data) {
    const ctx = document.getElementById('pmvChart').getContext('2d');
    
    const zones = getUniqueZones(data.optimized_timeseries);
    const mainZone = zones[0] || 'SPACE1-1';
    
    const pmvData = data.optimized_timeseries
        .filter(r => r.zone_name === mainZone)
        .map(r => ({ x: r.sim_time_hours, y: r.pmv }));
    
    const baselinePmv = data.baseline_timeseries
        .filter(r => r.zone_name === mainZone)
        .map(r => ({ x: r.sim_time_hours, y: r.pmv }));
    
    new Chart(ctx, {
        type: 'line',
        data: {
            datasets: [
                {
                    label: 'Optimized PMV',
                    data: pmvData,
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    fill: true,
                    tension: 0.3,
                    borderWidth: 2,
                    pointRadius: 0,
                },
                {
                    label: 'Baseline PMV',
                    data: baselinePmv,
                    borderColor: 'rgba(239, 68, 68, 0.5)',
                    backgroundColor: 'transparent',
                    tension: 0.3,
                    borderWidth: 1,
                    borderDash: [5, 5],
                    pointRadius: 0,
                },
                {
                    label: 'Comfort Upper Bound',
                    data: pmvData.map(p => ({ x: p.x, y: 0.5 })),
                    borderColor: 'rgba(245, 158, 11, 0.4)',
                    borderDash: [3, 3],
                    borderWidth: 1,
                    pointRadius: 0,
                    fill: false,
                },
                {
                    label: 'Comfort Lower Bound',
                    data: pmvData.map(p => ({ x: p.x, y: -0.5 })),
                    borderColor: 'rgba(245, 158, 11, 0.4)',
                    borderDash: [3, 3],
                    borderWidth: 1,
                    pointRadius: 0,
                    fill: false,
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'top', align: 'end' } },
            scales: {
                x: { type: 'linear', title: { display: true, text: 'Simulation Hours' }, grid: { display: false } },
                y: { 
                    title: { display: true, text: 'PMV Index' },
                    min: -1.5, max: 1.5,
                    grid: { color: 'rgba(255,255,255,0.03)' }
                }
            }
        }
    });
}

// ===== SETPOINT CHART =====
function renderSetpointChart(data) {
    const ctx = document.getElementById('setpointChart').getContext('2d');
    
    const setpoints = data.setpoint_history || [];
    
    const heatingData = setpoints
        .filter(s => s.setpoint_type === 'heating')
        .map(s => ({ x: s.sim_time_hours, y: s.new_value }));
    
    const coolingData = setpoints
        .filter(s => s.setpoint_type === 'cooling')
        .map(s => ({ x: s.sim_time_hours, y: s.new_value }));
    
    new Chart(ctx, {
        type: 'scatter',
        data: {
            datasets: [
                {
                    label: 'Heating Setpoint',
                    data: heatingData,
                    borderColor: '#ef4444',
                    backgroundColor: 'rgba(239, 68, 68, 0.5)',
                    pointRadius: 3,
                    showLine: true,
                    tension: 0.1,
                    borderWidth: 1.5,
                },
                {
                    label: 'Cooling Setpoint',
                    data: coolingData,
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.5)',
                    pointRadius: 3,
                    showLine: true,
                    tension: 0.1,
                    borderWidth: 1.5,
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'top', align: 'end' } },
            scales: {
                x: { title: { display: true, text: 'Simulation Hours' }, grid: { display: false } },
                y: { 
                    title: { display: true, text: 'Setpoint (°C)' },
                    min: 14, max: 30,
                    grid: { color: 'rgba(255,255,255,0.03)' }
                }
            }
        }
    });
}

// ===== BREAKDOWN CHART =====
function renderBreakdownChart(data) {
    const ctx = document.getElementById('breakdownChart').getContext('2d');
    
    // Aggregate by day
    const baselineByDay = aggregateByDay(data.baseline_timeseries, 'total_energy_kwh');
    const optimizedByDay = aggregateByDay(data.optimized_timeseries, 'total_energy_kwh');
    
    const labels = Object.keys(baselineByDay).map(d => `Day ${d}`);
    
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Baseline (kWh)',
                    data: Object.values(baselineByDay),
                    backgroundColor: 'rgba(239, 68, 68, 0.7)',
                    borderColor: '#ef4444',
                    borderWidth: 1,
                    borderRadius: 4,
                },
                {
                    label: 'AI-Optimized (kWh)',
                    data: Object.values(optimizedByDay),
                    backgroundColor: 'rgba(16, 185, 129, 0.7)',
                    borderColor: '#10b981',
                    borderWidth: 1,
                    borderRadius: 4,
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'top', align: 'end' } },
            scales: {
                y: { 
                    title: { display: true, text: 'Energy (kWh)' },
                    grid: { color: 'rgba(255,255,255,0.03)' }
                },
                x: { grid: { display: false } }
            }
        }
    });
}

// ===== DECISION LOG =====
function renderDecisionLog(decisions) {
    const container = document.getElementById('decision-log');
    
    if (!decisions || decisions.length === 0) {
        container.innerHTML = '<div class="decision-empty">No agent decisions recorded yet.</div>';
        return;
    }
    
    container.innerHTML = '';
    
    // Show last 50 decisions (most recent first)
    const recentDecisions = decisions.slice(-50).reverse();
    
    recentDecisions.forEach(d => {
        const item = document.createElement('div');
        item.className = 'decision-item';
        
        const actionsCount = (d.actions || []).length;
        const reasoning = (d.reasoning || 'No reasoning provided').substring(0, 200);
        
        item.innerHTML = `
            <div class="decision-header">
                <span class="decision-time">Hour ${d.sim_time_hours?.toFixed(1) || '?'} | Timestep #${d.timestep || '?'}</span>
                <span class="decision-actions">${actionsCount} action${actionsCount !== 1 ? 's' : ''}</span>
            </div>
            <div class="decision-reasoning">${escapeHtml(reasoning)}${reasoning.length >= 200 ? '...' : ''}</div>
        `;
        
        container.appendChild(item);
    });
}

// ===== HELPER FUNCTIONS =====
function aggregateByHour(timeseries, field) {
    const result = {};
    if (!timeseries) return result;
    
    timeseries.forEach(r => {
        const hour = Math.floor(r.sim_time_hours || 0) % 24;
        const key = String(hour).padStart(2, '0');
        result[key] = (result[key] || 0) + (r[field] || 0);
    });
    
    return result;
}

function aggregateByDay(timeseries, field) {
    const result = {};
    if (!timeseries) return result;
    
    timeseries.forEach(r => {
        const day = Math.floor((r.sim_time_hours || 0) / 24) + 1;
        result[day] = (result[day] || 0) + (r[field] || 0);
    });
    
    return result;
}

function getUniqueZones(timeseries) {
    if (!timeseries) return [];
    const zones = new Set();
    timeseries.forEach(r => {
        if (r.zone_name) zones.add(r.zone_name);
    });
    return Array.from(zones);
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ===== DEMO DATA GENERATOR =====
function generateDemoData() {
    const zones = ['SPACE1-1', 'SPACE2-1', 'SPACE3-1', 'SPACE4-1', 'SPACE5-1'];
    const baselineTimeseries = [];
    const optimizedTimeseries = [];
    const agentDecisions = [];
    const setpointHistory = [];
    
    // 7 days × 24 hours × 4 timesteps = 672 timesteps
    const totalTimesteps = 672;
    
    for (let t = 0; t < totalTimesteps; t++) {
        const simHours = t * 0.25;
        const hour = Math.floor(simHours) % 24;
        const day = Math.floor(simHours / 24) + 15;
        const isOccupied = hour >= 8 && hour <= 18;
        const isPeak = hour >= 14 && hour <= 17;
        
        // Outdoor temp (sinusoidal with daily variation)
        const outdoorTemp = 18 + 8 * Math.sin((hour - 6) * Math.PI / 12) + Math.random() * 2;
        
        zones.forEach(zone => {
            // Baseline: fixed setpoints, more energy used
            const baselineTemp = isOccupied ? 22 + Math.random() * 2 : 18 + Math.random() * 5;
            const baselineEnergy = isOccupied ? 0.8 + Math.random() * 0.4 : 0.3 + Math.random() * 0.2;
            const baselinePmv = (baselineTemp - 22) / 3.5;
            
            baselineTimeseries.push({
                timestep: t, sim_time_hours: simHours, zone_name: zone,
                zone_temp_c: +baselineTemp.toFixed(1),
                pmv: +baselinePmv.toFixed(2),
                occupancy: isOccupied ? Math.floor(Math.random() * 15) : 0,
                heating_sp: 21, cooling_sp: 24,
                total_energy_kwh: +baselineEnergy.toFixed(4),
                hvac_w: +(baselineEnergy * 4000).toFixed(0),
                outdoor_temp_c: +outdoorTemp.toFixed(1),
            });
            
            // Optimized: AI-controlled, less energy
            const savingsMultiplier = isOccupied ? 0.78 : 0.45;
            const optTemp = isOccupied ? 22.5 + Math.random() * 1.5 : 16 + Math.random() * 6;
            const optEnergy = baselineEnergy * savingsMultiplier;
            const optPmv = isOccupied ? (optTemp - 22) / 3.5 : baselinePmv;
            const optHeatSp = isOccupied ? 20 : 16;
            const optCoolSp = isOccupied ? (isPeak ? 25 : 24) : 28;
            
            optimizedTimeseries.push({
                timestep: t, sim_time_hours: simHours, zone_name: zone,
                zone_temp_c: +optTemp.toFixed(1),
                pmv: +optPmv.toFixed(2),
                occupancy: isOccupied ? Math.floor(Math.random() * 15) : 0,
                heating_sp: optHeatSp, cooling_sp: optCoolSp,
                total_energy_kwh: +optEnergy.toFixed(4),
                hvac_w: +(optEnergy * 4000).toFixed(0),
                outdoor_temp_c: +outdoorTemp.toFixed(1),
            });
        });
        
        // Agent decisions every hour
        if (t % 4 === 0 && t > 0) {
            const strategies = [
                'Night setback applied — widened dead band for all unoccupied zones.',
                'Peak demand avoidance — raised cooling setpoint to 25°C during peak hours.',
                'Occupancy-based control — reduced conditioning in empty conference zones.',
                'Pre-cooling initiated — starting HVAC 30 min before occupancy.',
                'Dead-band widened — mild outdoor conditions allow natural temperature float.',
                'Solar gain utilized — reduced heating in south-facing zones.',
                'All zones within comfort bounds — maintaining current setpoints.',
            ];
            
            agentDecisions.push({
                timestep: t,
                sim_time_hours: simHours,
                reasoning: strategies[Math.floor(Math.random() * strategies.length)],
                actions: [{ tool: 'set_cooling_setpoint', args: { zone_name: 'SPACE1-1', temperature: 24 + Math.random() * 2 } }],
            });
            
            // Setpoint changes
            zones.forEach(zone => {
                setpointHistory.push({
                    timestep: t, sim_time_hours: simHours, zone_name: zone,
                    setpoint_type: 'heating',
                    old_value: 21, new_value: isOccupied ? 20 : 16,
                });
                setpointHistory.push({
                    timestep: t, sim_time_hours: simHours, zone_name: zone,
                    setpoint_type: 'cooling',
                    old_value: 24, new_value: isOccupied ? (isPeak ? 25 : 24) : 28,
                });
            });
        }
    }
    
    const baselineTotal = baselineTimeseries.reduce((s, r) => s + r.total_energy_kwh, 0);
    const optimizedTotal = optimizedTimeseries.reduce((s, r) => s + r.total_energy_kwh, 0);
    const savingsPct = ((baselineTotal - optimizedTotal) / baselineTotal * 100);
    
    return {
        summary: {
            baseline_energy_kwh: +baselineTotal.toFixed(2),
            optimized_energy_kwh: +optimizedTotal.toFixed(2),
            energy_savings_kwh: +(baselineTotal - optimizedTotal).toFixed(2),
            energy_savings_percent: +savingsPct.toFixed(1),
            estimated_cost_savings_usd: +((baselineTotal - optimizedTotal) * 0.12).toFixed(2),
            baseline_comfort_violations: 45,
            optimized_comfort_violations: 12,
            total_agent_decisions: agentDecisions.length,
            total_setpoint_changes: setpointHistory.length,
        },
        baseline_timeseries: baselineTimeseries,
        optimized_timeseries: optimizedTimeseries,
        agent_decisions: agentDecisions,
        setpoint_history: setpointHistory,
    };
}

// ===== INIT =====
document.addEventListener('DOMContentLoaded', loadData);
