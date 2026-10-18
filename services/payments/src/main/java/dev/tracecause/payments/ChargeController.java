package dev.tracecause.payments;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ChargeController {

    record ChargeRequest(long orderId, long amountCents) {
    }

    record ChargeResponse(long paymentId, String status) {
    }

    private final PaymentStore store;

    public ChargeController(PaymentStore store) {
        this.store = store;
    }

    @PostMapping("/charge")
    public ChargeResponse charge(@RequestBody ChargeRequest request) {
        long paymentId = store.record(request.orderId(), request.amountCents());
        return new ChargeResponse(paymentId, "CAPTURED");
    }
}
