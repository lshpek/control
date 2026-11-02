export type Entity = Record<string, unknown> & { id: number };
export type DashboardData = { metrics: {clients:number;projects:number;open_tasks:number;services:number}; next_tasks:Array<{id:number;title:string;status:string;priority:string;due_date:string|null;project_id:number|null}>; recent_activity:Array<{id:number;actor:string;entity_type:string;entity_id:number|null;action:string;summary:string;created_at:string}>; service_summary:Array<{id:number;name:string;status:string;status_source:string;last_checked_at:string|null}> };

export type AuthUser = {
  id: number;
  username: string;
  roles: string[];
  permissions: Record<string, 'all' | 'assigned' | 'own_customer' | string>;
  customer_id: number | null;
  is_owner: boolean;
  must_change_password: boolean;
  last_login_at: string | null;
};

export type OrderStatus =
  | 'draft' | 'awaiting_proposal_approval' | 'awaiting_customer_information'
  | 'approved' | 'in_progress' | 'internal_review' | 'awaiting_customer_review'
  | 'changes_requested' | 'ready_for_delivery' | 'delivered' | 'completed'
  | 'on_hold' | 'cancelled';

export type OrderRecord = {
  id: number;
  order_number: string;
  client_id: number;
  project_id: number | null;
  client_name: string;
  title: string;
  scope: string;
  status: OrderStatus;
  client_visible_summary: string | null;
  internal_notes: string | null;
  amount: string | null;
  amount_type: 'estimate' | 'fixed';
  currency: string;
  target_delivery_date: string | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
};

export type OrderPortalRecord = {
  id: number;
  order_number: string;
  title: string;
  status: OrderStatus;
  client_visible_summary: string | null;
  amount: string | null;
  amount_type: 'estimate' | 'fixed';
  currency: string;
  target_delivery_date: string | null;
  created_at: string;
  updated_at: string;
};

export type OrderEvent = {
  id: number;
  event_type: string;
  from_status: string | null;
  to_status: string | null;
  message: string | null;
  created_at: string;
};

export type OrderMessage = {
  id: number;
  author_username: string | null;
  body: string;
  is_internal: boolean;
  created_at: string;
};

export type ClientOrderMessage = {
  id: number;
  author_username: string | null;
  body: string;
  created_at: string;
};
