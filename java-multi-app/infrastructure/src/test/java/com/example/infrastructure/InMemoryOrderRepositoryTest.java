package com.example.infrastructure;

import com.example.core.model.Order;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class InMemoryOrderRepositoryTest {
    private InMemoryOrderRepository repo;

    @BeforeEach
    void setUp() {
        repo = new InMemoryOrderRepository();
        repo.save(new Order("r1", 200.0));
    }

    @Test
    void findById_returnsOrder() {
        assertTrue(repo.findById("r1").isPresent());
    }

    @Test
    void save_updatesExisting() {
        Order updated = new Order("r1", 300.0);
        repo.save(updated);
        assertEquals(300.0, repo.findById("r1").get().getTotal(), 0.001);
        assertEquals(1, repo.findAll().size());
    }

    @Test
    void delete_removesOrder() {
        repo.delete("r1");
        assertFalse(repo.findById("r1").isPresent());
    }
}
