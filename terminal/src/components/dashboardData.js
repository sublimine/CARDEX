// ═══ DASHBOARD MOCK DATA ═══

// TradingView-style price history (90 days)
const BASE = 33500;
const genPrice = (i) => {
    const trend = i * 12;
    const noise = Math.sin(i * 0.7) * 800 + Math.cos(i * 1.3) * 400 + (Math.random() - 0.5) * 300;
    return Math.round(BASE + trend + noise);
};

export const PRICE_HISTORY = Array.from({ length: 90 }, (_, i) => {
    const d = new Date(2025, 11, 10 + i);
    const price = genPrice(i);
    const ma20 = i >= 20 ? Math.round(Array.from({ length: 20 }, (_, j) => genPrice(i - j)).reduce((a, b) => a + b) / 20) : null;
    return {
        date: `${d.getDate()}/${d.getMonth() + 1}`,
        price,
        ma20,
        volume: Math.floor(Math.random() * 60 + 20),
        high: price + Math.floor(Math.random() * 400),
        low: price - Math.floor(Math.random() * 400),
    };
});

export const MONTHLY_PNL = [
    { month: "Sep", revenue: 284000, costs: 241400, profit: 42600, cumProfit: 42600 },
    { month: "Oct", revenue: 312000, costs: 262080, profit: 49920, cumProfit: 92520 },
    { month: "Nov", revenue: 298000, costs: 253300, profit: 44700, cumProfit: 137220 },
    { month: "Dec", revenue: 345000, costs: 286350, profit: 58650, cumProfit: 195870 },
    { month: "Jan", revenue: 367000, costs: 300940, profit: 66060, cumProfit: 261930 },
    { month: "Feb", revenue: 389000, costs: 315390, profit: 73610, cumProfit: 335540 },
    { month: "Mar", revenue: 412000, costs: 329600, profit: 82400, cumProfit: 417940 },
];

export const DEAL_PIPELINE = [
    { stage: "Sourced", count: 847, value: 28400000, color: "#3B82F6" },
    { stage: "Analyzed", count: 412, value: 14200000, color: "#8B5CF6" },
    { stage: "Approved", count: 186, value: 7800000, color: "#06B6D4" },
    { stage: "In Transit", count: 67, value: 3200000, color: "#F59E0B" },
    { stage: "Delivered", count: 234, value: 9100000, color: "#22C55E" },
];

export const ROUTE_PERFORMANCE = [
    { route: "DE → ES", volume: 342, margin: 14.8, avgDays: 12, trend: +2.3, flag: "🇩🇪→🇪🇸" },
    { route: "NL → FR", volume: 187, margin: 12.1, avgDays: 8, trend: +5.1, flag: "🇳🇱→🇫🇷" },
    { route: "BE → ES", volume: 156, margin: 16.2, avgDays: 14, trend: -1.4, flag: "🇧🇪→🇪🇸" },
    { route: "DE → FR", volume: 134, margin: 11.8, avgDays: 6, trend: +3.7, flag: "🇩🇪→🇫🇷" },
    { route: "CH → DE", volume: 98, margin: 18.4, avgDays: 4, trend: +8.2, flag: "🇨🇭→🇩🇪" },
    { route: "DE → NL", volume: 89, margin: 9.6, avgDays: 5, trend: -0.8, flag: "🇩🇪→🇳🇱" },
];

export const TAX_BREAKDOWN = [
    { name: "Margin Scheme", value: 48, color: "#22C55E" },
    { name: "Deductible VAT", value: 31, color: "#3B82F6" },
    { name: "Standard Rate", value: 14, color: "#F59E0B" },
    { name: "Under Review", value: 7, color: "#EF4444" },
];

export const HEATMAP_DATA = {
    models: ["BMW 3", "Audi A4", "MB C", "Golf", "Macan", "X3", "Q5", "E-Class"],
    countries: ["DE", "ES", "FR", "NL", "BE", "CH"],
    scores: [
        [82, 94, 78, 71, 65, 58], [76, 88, 91, 82, 74, 62], [68, 72, 85, 90, 78, 55],
        [91, 86, 74, 68, 82, 48], [54, 62, 58, 45, 52, 92], [78, 82, 70, 88, 76, 64],
        [72, 78, 86, 74, 68, 56], [65, 70, 82, 76, 72, 88],
    ],
};

export const RADAR_OPPORTUNITIES = [
    { id: "OP-2841", vehicle: "BMW M4 Competition", year: 2023, km: 12500, origin: "DE", dest: "ES", buyPrice: 82000, sellPrice: 93200, margin: 11200, marginPct: 13.0, score: 96, taxStatus: "DEDUCTIBLE", daysOnMarket: 3, image: "https://images.unsplash.com/photo-1617531653332-bd46c24f2068?w=400&q=80" },
    { id: "OP-2839", vehicle: "Audi RSQ8 Vorsprung", year: 2022, km: 34000, origin: "FR", dest: "ES", buyPrice: 105000, sellPrice: 120000, margin: 15000, marginPct: 13.4, score: 88, taxStatus: "MARGIN", daysOnMarket: 7, image: "https://images.unsplash.com/photo-1606664515524-ed2f786a0bd6?w=400&q=80" },
    { id: "OP-2837", vehicle: "Porsche Cayenne S", year: 2023, km: 18000, origin: "CH", dest: "DE", buyPrice: 89000, sellPrice: 98200, margin: 9200, marginPct: 10.3, score: 91, taxStatus: "DEDUCTIBLE", daysOnMarket: 2, image: "https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=400&q=80" },
    { id: "OP-2835", vehicle: "Mercedes GLC 300 AMG", year: 2024, km: 8000, origin: "BE", dest: "ES", buyPrice: 51200, sellPrice: 57300, margin: 6100, marginPct: 11.9, score: 94, taxStatus: "MARGIN", daysOnMarket: 5, image: "https://images.unsplash.com/photo-1618843479313-40f8afb4b4d8?w=400&q=80" },
    { id: "OP-2833", vehicle: "Volvo EX30 Twin", year: 2024, km: 5000, origin: "BE", dest: "FR", buyPrice: 42000, sellPrice: 48500, margin: 6500, marginPct: 14.6, score: 98, taxStatus: "DEDUCTIBLE", daysOnMarket: 1, image: "https://images.unsplash.com/photo-1614200179396-2bdb77ebf81b?w=400&q=80" },
    { id: "OP-2831", vehicle: "Tesla Model Y LR", year: 2023, km: 22000, origin: "NL", dest: "ES", buyPrice: 38400, sellPrice: 44200, margin: 5800, marginPct: 15.1, score: 85, taxStatus: "MARGIN", daysOnMarket: 9, image: "https://images.unsplash.com/photo-1560958089-b8a1929cea89?w=400&q=80" },
];

export const ALERTS = [
    { type: "fraud", msg: "Fraud alert: VIN WBA53EC06P cloned — flagged by Interpol", time: "12min", severity: "critical" },
    { type: "price", msg: "Price drop: BMW X3 xDrive30d below market avg by 8.3%", time: "28min", severity: "opportunity" },
    { type: "tax", msg: "3 vehicles reclassified: MARGIN → DEDUCTIBLE", time: "1h", severity: "info" },
];

export const PERFORMANCE_DAILY = Array.from({ length: 30 }, (_, i) => ({
    day: i + 1,
    profit: Math.floor(Math.random() * 18000 + 5000),
}));

// NLC Waterfall breakdown
export const NLC_WATERFALL = [
    { name: "Purchase", value: 32400, total: 32400, color: "#3B82F6" },
    { name: "Transport", value: 850, total: 33250, color: "#8B5CF6" },
    { name: "Insurance", value: 180, total: 33430, color: "#8B5CF6" },
    { name: "Customs", value: 320, total: 33750, color: "#F59E0B" },
    { name: "FX Hedge", value: 45, total: 33795, color: "#F59E0B" },
    { name: "NLC", value: 33795, total: 33795, color: "#06B6D4", isTotal: true },
    { name: "Sell Price", value: 38200, total: 38200, color: "#22C55E", isTotal: true },
    { name: "Net Margin", value: 4405, total: 4405, color: "#22C55E", isTotal: true },
];

// Vehicle DNA timeline
export const VEHICLE_DNA = [
    { date: "2024-03-10", event: "Listed on CARDEX", detail: "Mileage: 15.000 km · Condition: 9.2/10", type: "listing", icon: "📍" },
    { date: "2024-02-28", event: "Technical Inspection", detail: "Result: PASS ✓ · No significant issues", type: "inspection", icon: "🔍" },
    { date: "2024-01-15", event: "Ownership Transfer", detail: "BMW München AG → AutoHaus Schmidt", type: "transfer", icon: "🏢" },
    { date: "2023-11-20", event: "Market Valuation", detail: "Estimated: €34.200 · Market avg: €33.800", type: "valuation", icon: "📊" },
    { date: "2023-09-10", event: "Full Service", detail: "BMW Dealer · Oil, brakes, filters", type: "service", icon: "🔧" },
    { date: "2023-03-15", event: "First Registration", detail: "Munich, Germany · New delivery", type: "registration", icon: "🚗" },
];
