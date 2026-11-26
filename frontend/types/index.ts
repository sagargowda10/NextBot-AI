export type Role = "ADMIN" | "CUSTOMER" | "SUPPORT_AGENT" | "INVENTORY_MANAGER";

export interface User { id: number; email: string; full_name: string; roles: Role[] }
export interface TokenPair { access_token: string; refresh_token: string; expires_in: number }
export interface Page<T> { items: T[]; total: number; page: number; size: number }

export interface Variant { id: number; sku: string; size?: string | null; colour?: string | null; price: string; stock_available: number }
export interface Product {
  id: number; name: string; slug: string; brand: string; category: string; price: string; mrp: string;
  discount_percent: number; rating: number; image_url?: string | null; in_stock: boolean; variants: Variant[]; score?: number | null;
}
export interface ProductDetail extends Product {
  description: string; specifications: Record<string, string>; images: string[]; review_count: number;
}

export interface CartItem {
  id: number; variant_id: number; product_id: number; product_name: string; sku: string; size?: string | null;
  colour?: string | null; unit_price: string; quantity: number; line_total: string; image_url?: string | null;
}
export interface Cart {
  id: number; items: CartItem[]; subtotal: string; discount: string; tax: string; shipping: string; total: string;
  coupon_code?: string | null; coupon_error?: string | null;
}

export interface OrderItem { id: number; product_id: number; variant_id: number; product_name: string; sku: string; quantity: number; unit_price: string; line_total: string }
export interface Order {
  id: number; order_number: string; user_id: number; status: string; subtotal: string; discount: string; tax: string;
  shipping_fee: string; total: string; coupon_code?: string | null; items: OrderItem[]; shipping_pincode?: string | null;
  created_at: string; delivered_at?: string | null; risk_score?: number | null; payment_status?: string | null;
}
export interface ShipmentEvent { status: string; at: string; location?: string | null; note?: string | null }
export interface Shipment {
  id: number; order_id: number; carrier: string; tracking_number: string; status: string;
  estimated_delivery?: string | null; events: ShipmentEvent[]; is_simulated: boolean;
}
export interface ReturnRequest {
  id: number; order_id: number; order_number?: string | null; status: string; reason: string; refund_amount: string;
  eligible: boolean; eligibility_message: string; approval_request_id?: number | null; created_at: string;
}
export interface StockLevel {
  inventory_id: number; variant_id: number; product_id: number; product_name: string; sku: string; warehouse?: string | null;
  quantity: number; reserved: number; available: number; low_stock: boolean;
}
export interface Address { id: number; label: string; line1: string; line2?: string | null; city: string; state: string; pincode: string; phone: string; is_default: boolean }

export interface AgentStep { agent: string; success: boolean; summary: string; duration_ms: number; tools: string[] }
export interface ChatSource { id: string; title: string; source?: string; score: number; excerpt: string }
export interface ChatResponse {
  conversation_id: number; reply: string; intent: string; products: Product[]; data: Record<string, unknown>;
  agents: AgentStep[]; sources: ChatSource[]; suggestions: string[]; demo_mode: boolean; ai_provider: string; requires_approval: boolean;
}
export interface Conversation { id: number; title: string; channel: string; status: string; created_at: string; messages?: { role: string; content: string }[] }

export interface PluginInfo {
  id: string; name: string; version: string; description: string; status: string; health: string;
  requires_credentials: boolean; mode: string; registered_at?: string;
  actions: { name: string; description: string; permission: string }[];
  stats: { executions: number; successes: number; failures: number; avg_duration_ms: number; last_execution_at?: string | null; last_error?: string | null };
  config: Record<string, unknown>;
}
export interface PluginExecution { id: string; plugin_id: string; action: string; agent?: string | null; success: boolean; duration_ms: number; error?: string | null; started_at: string }

export interface AgentInfo {
  name: string; display_name: string; description: string; is_supervisor: boolean; allowed_tools: string[];
  max_iterations: number; timeout_s: number; executions: number; successes: number; failures: number; success_rate: number; avg_duration_ms: number;
}
export interface AgentExecution { id: string; agent: string; intent?: string | null; success: boolean; duration_ms: number; tool_calls: number; error?: string | null; started_at: string }

export interface Approval {
  id: number; action: string; status: string; summary: string; payload: Record<string, unknown>; requested_by_agent?: string | null;
  review_note?: string | null; result?: Record<string, unknown> | null; created_at: string;
}
export interface Dashboard {
  revenue_30d: string; orders_30d: number; customers: number; products: number; low_stock_items: number; open_returns: number;
  pending_approvals: number; plugins_enabled: number; plugins_total: number; agent_executions_24h: number; agent_success_rate: number;
  top_products: { product_id: number; name: string; units: number; revenue: string }[];
  sales_by_day: { date: string; revenue: string; orders: number }[]; orders_by_status: Record<string, number>;
}
export interface SalesSummary { period: string; revenue: string; orders: number; average_order_value: string; by_day: { date: string; revenue: string; orders: number }[] }
export interface NotificationItem { id: number; channel: string; template: string; recipient: string; subject?: string | null; body: string; status: string; created_at: string }
