package com.example.batch;

import com.example.core.model.Order;
import com.example.infrastructure.InMemoryOrderRepository;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class OrderExpiryJobTest {
    @Test
    void run_expiresPendingOrders() {
        InMemoryOrderRepository repo = new InMemoryOrderRepository();
        repo.save(new Order("x1", 10.0));
        repo.save(new Order("x2", 20.0));
        repo.findById("x2").get().setStatus("CANCELLED");
        repo.save(repo.findById("x2").get());

        OrderExpiryJob job = new OrderExpiryJob(repo);
        int count = job.run();

        assertEquals(1, count);
        assertEquals("EXPIRED", repo.findById("x1").get().getStatus());
        assertEquals("CANCELLED", repo.findById("x2").get().getStatus());
    }
}
