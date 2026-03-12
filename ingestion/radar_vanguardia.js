const Redis = require('ioredis');
const redis = new Redis({ host: '127.0.0.1', port: 6379 });
const { Client } = require('pg');

const pgClient = new Client({
    connectionString: 'postgres://cardex_admin:alpha_secure_99@127.0.0.1:5432/cardex_core?sslmode=disable'
});

// Semillas de prueba: Mezcla de Tier 1 hiper-defendidos y Tier 2/3 vulnerables
const TARGET_DOMAINS = [
    'https://www.mobile.de',       // Datadome (Amenaza Crítica)
    'https://www.autoscout24.es',  // Cloudflare Bot Management
    'https://www.coches.net',      // Akamai
    'https://www.flexicar.es',     // Tier 2 (Generalmente vulnerable)
    'https://www.clicars.com'      // Tier 2 (Generalmente vulnerable)
];

async function analyzePerimeter(url) {
    console.log(`[RADAR] Escaneando perímetro: ${url}`);
    try {
        // Petición deliberadamente ruidosa para provocar al WAF
        const response = await fetch(url, {
            headers: { 'User-Agent': 'Cardex-Recon-Spider/1.0' },
            signal: AbortSignal.timeout(5000)
        });

        const headers = response.headers;
        let wafSignature = 'NONE';
        let threatLevel = 'LOW';

        // Análisis de firmas de red
        if (headers.get('x-datadome') || headers.get('set-cookie')?.includes('datadome')) {
            wafSignature = 'DATADOME';
            threatLevel = 'CRITICAL';
        } else if (headers.get('server')?.toLowerCase().includes('cloudflare') || response.status === 403) {
            wafSignature = 'CLOUDFLARE';
            threatLevel = 'MEDIUM';
        } else if (headers.get('set-cookie')?.includes('ak_bmsc') || headers.get('server')?.toLowerCase().includes('akamai')) {
            wafSignature = 'AKAMAI';
            threatLevel = 'HIGH';
        }

        return { url, status: response.status, wafSignature, threatLevel };

    } catch (error) {
        return { url, status: 0, wafSignature: 'TIMEOUT_OR_BLOCK', threatLevel: 'UNKNOWN' };
    }
}

(async () => {
    await pgClient.connect();
    console.log('[VANGUARDIA] Motor de reconocimiento inicializado.');

    const pipeline = redis.pipeline();

    for (const domain of TARGET_DOMAINS) {
        const intel = await analyzePerimeter(domain);

        if (intel.threatLevel === 'CRITICAL' || intel.threatLevel === 'HIGH' || intel.wafSignature !== 'NONE') {
            console.log(`[BLOQUEO] ${intel.url} defendido por ${intel.wafSignature}. Aislando en cuarentena PostgreSQL.`);
            await pgClient.query(
                `INSERT INTO fortified_targets (domain, waf_signature, http_status, threat_level) 
                 VALUES ($1, $2, $3, $4) 
                 ON CONFLICT (domain) DO UPDATE SET detected_at = CURRENT_TIMESTAMP, waf_signature = $2;`,
                [intel.url, intel.wafSignature, intel.status, intel.threatLevel]
            );
        } else {
            console.log(`[VULNERABLE] ${intel.url} sin escudo detectado. Derivando a cola de extracción masiva.`);
            pipeline.rpush('queue:tier2_extraction', intel.url);
        }
    }

    await pipeline.exec();
    console.log('[VANGUARDIA] Barrido completado. Nodos vulnerables en Redis listos para asalto.');
    
    await pgClient.end();
    await redis.quit();
    process.exit(0);
})();
