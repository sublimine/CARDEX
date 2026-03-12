const Redis = require('ioredis');
const redis = new Redis({ host: '127.0.0.1', port: 6379 });

const SCRAPINGBEE_API_KEY = 'process.env.SCRAPINGBEE_API_KEY';

// Objetivo: Últimos vehículos publicados en España (ordenados por edad)
const TARGET_URL = 'https://www.autoscout24.es/lst/?sort=age&desc=1&size=20';

(async () => {
    console.log('[MOTOR DE ASALTO] Inicializando barrido táctico sobre mercado ES...');
    
    // Disparo premium sin JavaScript para ahorrar tiempo (el HTML crudo contiene los datos)
    const scrapingBeeUrl = 'https://app.scrapingbee.com/api/v1/?api_key=' + SCRAPINGBEE_API_KEY + '&url=' + encodeURIComponent(TARGET_URL) + '&premium_proxy=true&render_js=false';

    try {
        const response = await fetch(scrapingBeeUrl);

        if (!response.ok) {
            console.error('[FATAL] Bloqueo en nodo (' + response.status + ').');
            await redis.quit();
            return;
        }

        const htmlContent = await response.text();
        console.log('[MOTOR DE ASALTO] HTML interceptado. Perforando el DOM...');

        // Expresión regular quirúrgica para extraer el JSON interno (__NEXT_DATA__) que usan los portales modernos
        const nextDataRegex = /<script id="__NEXT_DATA__" type="application\/json">(.*?)<\/script>/;
        const match = nextDataRegex.exec(htmlContent);

        let extractedCount = 0;
        const pipeline = redis.pipeline();

        if (match && match[1]) {
            console.log('[MOTOR DE ASALTO] Vena de datos principal (JSON) localizada.');
            const data = JSON.parse(match[1]);
            
            // Navegación por el árbol JSON de AutoScout24
            const listings = data.props?.pageProps?.listings || [];
            
            listings.forEach(item => {
                const vin = item.id || 'N/A';
                const price = item.price?.priceRaw || 0;
                const url = 'https://www.autoscout24.es' + (item.url || '');
                
                pipeline.xadd('stream:darkpool_ready', '*', 
                    'vin', 'AS24_' + vin, 
                    'nlc', price, 
                    'legal_status', 'PENDING_NLP', 
                    'quote_id', 'AS24_' + vin, 
                    'source_url', url,
                    'image_url', ''
                );
                extractedCount++;
            });
        } else {
            // Plan B: Si mutan el JSON, extraemos por fuerza bruta atributos HTML
            console.log('[MOTOR DE ASALTO] JSON oculto. Cambiando a extracción por fuerza bruta (Regex)...');
            const articleRegex = /<article[^>]+data-item-group="([^"]+)"[^>]*>.*?data-price="([^"]+)"/gs;
            let artMatch;
            while ((artMatch = articleRegex.exec(htmlContent)) !== null) {
                const vin = artMatch[1];
                const price = artMatch[2];
                pipeline.xadd('stream:darkpool_ready', '*', 
                    'vin', 'AS24_' + vin, 
                    'nlc', price, 
                    'legal_status', 'PENDING_NLP', 
                    'quote_id', 'AS24_' + vin, 
                    'source_url', 'https://www.autoscout24.es/ofertas/' + vin,
                    'image_url', ''
                );
                extractedCount++;
            }
        }

        if (extractedCount > 0) {
            await pipeline.exec();
            console.log('[DISCO] ' + extractedCount + ' ACTIVOS REALES inyectados en el Dark Pool.');
        } else {
            console.log('[ALERTA] Estructura HTML mutada. No se pudieron extraer vehículos.');
        }

    } catch (error) {
        console.error('[ERROR DE SISTEMA]', error.message);
    } finally {
        await redis.quit();
        console.log('[MOTOR DE ASALTO] Apagado. Mira tu pantalla de Next.js AHORA.');
    }
})();
