# Flow Diagram and Model Diff Examples

Detailed guidance and worked examples for steps 5.2 (Identifying the affected flows) and 5.3
(Model/domain/POJO/DTO changes) of the code-review workflow. Load this file when producing the
flow diagrams or model diff trees called for in those steps.

## 5.2 Identifying the affected flows

1. **Entry Point**: REST endpoint, message topic, scheduled job, or any other external integration
2. **Layer Transitions**: Web → Domain → Persistence → External
3. **Changed Components**: Mark with 🔵 or 🟢
4. **New Logic**: Highlight new calculators, validators, services with 🟢
5. **Data Transformations**: Show mapper invocations

Once the flows are identified, present the whole flow diagram for each flow, reflecting the
changed part.

Example:

```
┌─────────────────────────────────────────────────────────────────────┐
│                POST /api/v1/subscriptions/initiate                  │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  WEB LAYER (my-service-web)                                         │
│  ├─ OrderInitiationController                                       │
│  │   └─ Receives JsonOrderInitiationRequest                         │
│  │                                                                  │
│  └─ JsonOrderMapper 🔵                                              │
│      └─ Transforms: JSON DTO 🔵 → Domain Model 🔵                   │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  DOMAIN LAYER (my-service-domain)                                   │
│  └─ OrderInitiationService 🔵                                       │
│      ├─ 1. Business logic validation                                │
│      ├─ 2. Calculate order schedule 🟢                              │
│      ├─ 3. Create Order aggregate                                   │
│      ├─ 4. Call OrderRepository.save()                              │
│      └─ 5. Call PublicationService.publish()                        │
└─────────────────────────────────────────────────────────────────────┘
                                        │
                        ┌───────────────┴───────────────┐
                        ▼                               ▼
┌────────────────────────────────────┐  ┌────────────────────────────────┐
│ PERSISTENCE LAYER                  │  │ EXTERNAL LAYER                 │
│ (my-service-persistence)           │  │ (my-service-external)          │
│                                    │  │                                │
│ ├─ JdbcOrderRepository             │  │ └─ PublicationService          │
│ │   └─ INSERT order                │  │     └─ Kafka event publisher   │
│ │       (MASTER DB)                │  │         order.initiated        │
│ │                                  │  │                                │
│ ├─ JdbcOrderItemRepository         │  │                                │
│ │   └─ INSERT order items          │  │                                │
│ │                                  │  │                                │
│ ├─ JdbcOrderActionRepository       │  │                                │
│ │   └─ INSERT audit trail          │  │                                │
│ │                                  │  │                                │
│ └─ JdbcOrderSnapshotRepo           │  │                                │
│     └─ INSERT order snapshot       │  │                                │
│                                    │  │                                │
│ [MySQL Master]                     │  │ [Kafka]                        │
└────────────────────────────────────┘  └────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│  RESPONSE FLOW                                                      │
│  ├─ Domain → JsonOrderMapper 🔵                                     │
│  └─ JsonOrderInitiationResponse                                     │
└─────────────────────────────────────────────────────────────────────┘
```

Legend:
- 🔴 = Removed component
- 🟢 = Added component
- ⚪ = Unchanged component
- 🔵 = Transitively changed component

## 5.3 Model/domain/POJO/DTO changes approach

- If the structure is changed, analyze the full fields hierarchy/tree of the class (starting from the root class)
- Identify the root aggregate first (e.g., Subscription, Order, User) — usually used by major components in the flow from 5.2
- Show complete nested hierarchy from root to changed field
- Never present isolated nested objects without parent context
- Combine nested structures into a single tree (not separate sections)
- Show all intermediate levels — no skipped fields
- Draw a human-readable diff tree marking: red for removed nodes, green for new nodes, blue for
  changed object nodes, white for unchanged nodes/fields
- Always include the inner fields structure of the changed/removed/added nodes

Example:

```
com.example.payments
└── config
└─🔵 OrderConfig
├── ⚪ orderId: String
├── 🔴 customerId: String
├── 🟢 customer: CustomerInfo
│   ├── 🟢 id: String
│   ├── 🟢 email: String
│   └── 🟢 tier: Integer
├── ⚪ amount: BigDecimal
├── 🔴 paymentMethod: String
├── 🟢 payment: PaymentInfo
│   ├── 🟢 method: String
│   ├── 🟢 provider: String
│   └── 🟢 fees: Money
│       ├── 🟢 amount: BigDecimal
│       └── 🟢 currency: Currency
├── 🔴 status: String
├── 🟢 status: OrderStatus(enum: 🟢VALUE1, ⚪VALUE2, 🔴VALUE3)
├── ⚪ createdAt: Instant
├── 🔴 shippingAddress: String
└── 🟢 shipping: ShippingInfo
├── 🔵 address: Address
│   ├── 🔴 street: String
│   ├── 🟢 city: String
│   └── 🟢 postalCode: String
├── 🟢 carrier: String
└── 🔵 trackingNumber: 🟢String 🔴Integer
```

Legend:
- 🔴 = Removed field
- 🟢 = Added field
- ⚪ = Unchanged field
- 🔵 = Changed object field
