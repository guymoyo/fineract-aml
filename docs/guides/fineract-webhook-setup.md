# Fineract Webhook Setup

This guide explains how to configure Apache Fineract to send transaction events to the AML service.

## Overview

Fineract supports webhooks that fire when specific events occur (deposits, withdrawals, transfers). We configure Fineract to POST these events to our AML service's webhook endpoint.

## Step 1: Configure Fineract Webhook

### Option A: Fineract Built-in Webhooks

If your Fineract version supports the webhook/event system:

1. Log into Fineract admin UI
2. Navigate to **System → Webhooks**
3. Create a new webhook:
   - **URL**: `http://aml-api.aml.svc.cluster.local:8000/api/v1/webhook/fineract`
     (internal Kubernetes URL — adjust based on your deployment)
   - **Events**: Select `SAVINGS_DEPOSIT`, `SAVINGS_WITHDRAWAL`, `LOAN_DISBURSEMENT`, `LOAN_REPAYMENT`
   - **Content-Type**: `application/json`
   - **Secret**: Set the same value as `AML_FINERACT_WEBHOOK_SECRET`

### Option B: Custom Event Listener (Spring Boot)

If you need more control, add a Spring event listener in your Fineract deployment:

```java
@Component
public class AmlWebhookPublisher {

    private final RestTemplate restTemplate;
    private final String amlWebhookUrl;

    public AmlWebhookPublisher(
        RestTemplate restTemplate,
        @Value("${aml.webhook.url}") String amlWebhookUrl
    ) {
        this.restTemplate = restTemplate;
        this.amlWebhookUrl = amlWebhookUrl;
    }

    @TransactionalEventListener
    public void onSavingsDeposit(SavingsDepositEvent event) {
        var payload = Map.of(
            "transaction_id", event.getTransactionId(),
            "account_id", event.getAccountId(),
            "client_id", event.getClientId(),
            "transaction_type", "deposit",
            "amount", event.getAmount(),
            "currency", event.getCurrency(),
            "transaction_date", event.getTransactionDate().toString()
        );
        sendWebhook(payload);
    }

    @TransactionalEventListener
    public void onSavingsWithdrawal(SavingsWithdrawalEvent event) {
        var payload = Map.of(
            "transaction_id", event.getTransactionId(),
            "account_id", event.getAccountId(),
            "client_id", event.getClientId(),
            "transaction_type", "withdrawal",
            "amount", event.getAmount(),
            "currency", event.getCurrency(),
            "transaction_date", event.getTransactionDate().toString()
        );
        sendWebhook(payload);
    }

    private void sendWebhook(Map<String, Object> payload) {
        try {
            var headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            headers.set("X-Webhook-Signature", computeHmac(payload));

            var request = new HttpEntity<>(payload, headers);
            restTemplate.postForEntity(amlWebhookUrl, request, String.class);
        } catch (Exception e) {
            log.error("Failed to send AML webhook", e);
            // Consider retry logic or dead letter queue
        }
    }

    private String computeHmac(Map<String, Object> payload) {
        // HMAC-SHA256 signature for webhook verification
        var json = new ObjectMapper().writeValueAsString(payload);
        var mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(webhookSecret.getBytes(), "HmacSHA256"));
        return Hex.encodeHexString(mac.doFinal(json.getBytes()));
    }
}
```

### Option C: Database Polling (Fallback)

If webhooks are not available, the AML service can poll Fineract's API:

```python
# Add to Celery beat schedule
"poll-fineract-transactions": {
    "task": "app.tasks.polling.poll_new_transactions",
    "schedule": 60.0,  # Every minute
}
```

This is less ideal but works as a fallback.

## Step 2: Verify Connectivity

### From within the Kubernetes cluster:

```bash
# Test webhook endpoint is reachable
kubectl exec -n fineract deploy/fineract-server -- \
  curl -s http://aml-api.aml.svc.cluster.local:8000/health
```

### Send a test webhook:

```bash
curl -X POST http://localhost:8000/api/v1/webhook/fineract \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "TEST-001",
    "account_id": "ACC-001",
    "client_id": "CLI-001",
    "transaction_type": "deposit",
    "amount": 1500.00,
    "currency": "USD",
    "transaction_date": "2025-06-15T14:30:00Z"
  }'
```

Expected response:
```json
{
  "status": "accepted",
  "transaction_id": "...",
  "message": "Transaction queued for AML analysis"
}
```

## Step 3: Network Configuration

### Kubernetes Network Policy (optional but recommended)

Allow traffic only from Fineract namespace to AML webhook:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-fineract-webhook
  namespace: aml
spec:
  podSelector:
    matchLabels:
      app: aml-api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              name: fineract
      ports:
        - protocol: TCP
          port: 8000
```

## Webhook Payload Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `transaction_id` | string | Yes | Fineract transaction ID |
| `account_id` | string | Yes | Savings/loan account ID |
| `client_id` | string | Yes | Fineract client ID |
| `transaction_type` | enum | Yes | `deposit`, `withdrawal`, `transfer` |
| `amount` | float | Yes | Transaction amount (> 0) |
| `currency` | string | No | ISO 4217 code (default: USD) |
| `transaction_date` | datetime | Yes | ISO 8601 timestamp |
| `counterparty_account_id` | string | No | For transfers |
| `counterparty_name` | string | No | For transfers |
| `description` | string | No | Transaction description |
