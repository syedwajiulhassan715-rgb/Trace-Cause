package dev.tracecause.inventory;

import java.util.Optional;

@FunctionalInterface
public interface StockStore {

    /** Records a reservation and returns the unit price, or empty if the SKU is unknown. */
    Optional<Long> reserve(String sku, int quantity);
}
