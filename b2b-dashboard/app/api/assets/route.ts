import { NextResponse } from 'next/server';
import { Pool } from 'pg';

const pool = new Pool({
  connectionString:
    process.env.DATABASE_URL ||
    'postgres://cardex_admin:alpha_secure_99@127.0.0.1:5432/cardex_core?sslmode=disable',
});

export async function GET() {
  try {
    const client = await pool.connect();
    const result = await client.query(`
      SELECT shadow_id, nlc_price, deep_payload
      FROM assets
      ORDER BY created_at DESC
      LIMIT 500
    `);
    client.release();

    const formatted = result.rows.map((row) => ({
      vin: row.shadow_id,
      nlc: parseFloat(row.nlc_price),
      legal_status: row.deep_payload?.legal_status ?? 'UNKNOWN',
      quote_id: row.shadow_id,
    }));

    return NextResponse.json(formatted);
  } catch (error) {
    console.error('[assets] DB error:', error);
    return NextResponse.json(
      { error: 'Fallo de base de datos' },
      { status: 500 }
    );
  }
}
