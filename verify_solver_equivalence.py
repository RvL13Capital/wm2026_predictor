#!/usr/bin/env python3
import random
import sys
import os
import time

# Ensure project root is in the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from solver import get_points, solve_optimal_tip_from_grid

def naive_solve(grid, max_tip):
    expected_points = {}
    
    # Flatten the grid
    flat_probs = []
    if isinstance(grid, dict):
        for g_a, row in grid.items():
            for g_b, val in row.items():
                flat_probs.append(((g_a, g_b), val))
    else:
        flat_probs = []
        for g_a, row in enumerate(grid):
            for g_b, val in enumerate(row):
                flat_probs.append(((g_a, g_b), val))
                
    for t_a in range(max_tip + 1):
        for t_b in range(max_tip + 1):
            ev = 0.0
            for (g_a, g_b), val in flat_probs:
                ev += val * get_points(t_a, t_b, g_a, g_b)
            expected_points[(t_a, t_b)] = ev
            
    sorted_tips = sorted(expected_points.items(), key=lambda x: x[1], reverse=True)
    return sorted_tips

def generate_random_grid_dict(size):
    grid = {}
    total = 0.0
    for x in range(size):
        grid[x] = {}
        for y in range(size):
            val = random.random()
            grid[x][y] = val
            total += val
    # Normalize
    for x in range(size):
        for y in range(size):
            grid[x][y] /= total
    return grid

def generate_random_grid_list(size):
    grid = []
    total = 0.0
    for x in range(size):
        row = []
        for y in range(size):
            val = random.random()
            row.append(val)
            total += val
        grid.append(row)
    # Normalize
    for x in range(size):
        for y in range(size):
            grid[x][y] /= total
    return grid

def run_equivalence_test(num_iterations=10000):
    print(f"Starting solver equivalence test with {num_iterations} iterations...")
    
    start_time = time.time()
    mismatches = 0
    total_checked = 0
    
    for i in range(num_iterations):
        size = random.randint(1, 15)
        max_tip = random.randint(0, 8)
        grid_type = random.choice(["dict", "list"])
        
        if grid_type == "dict":
            grid = generate_random_grid_dict(size)
        else:
            grid = generate_random_grid_list(size)
            
        # Run naive solver
        naive_tips = naive_solve(grid, max_tip)
        
        # Run optimized solver
        opt_tips, _, _ = solve_optimal_tip_from_grid(grid, max_tip)
        
        # Compare length
        if len(naive_tips) != len(opt_tips):
            print(f"Mismatch in tip list length at iteration {i}: Naive={len(naive_tips)}, Opt={len(opt_tips)}")
            mismatches += 1
            continue
            
        # Compare each tip and EV
        matched = True
        for (n_tip, n_ev), (o_tip, o_ev) in zip(naive_tips, opt_tips):
            if n_tip != o_tip:
                # If EVs are extremely close, order could be different due to sorting stability
                if abs(n_ev - o_ev) > 1e-9:
                    print(f"Mismatch in tip order at iteration {i}: Naive={n_tip} (EV={n_ev:.6f}), Opt={o_tip} (EV={o_ev:.6f})")
                    matched = False
                    break
            if abs(n_ev - o_ev) > 1e-9:
                print(f"Mismatch in EV at iteration {i}: Tip={n_tip}, Naive EV={n_ev:.6f}, Opt EV={o_ev:.6f}")
                matched = False
                break
                
        if not matched:
            mismatches += 1
        total_checked += 1
        
        if (i + 1) % 2000 == 0:
            print(f"Completed {i + 1}/{num_iterations} iterations...")

    elapsed = time.time() - start_time
    print(f"\nEquivalence Test Finished in {elapsed:.2f}s")
    print(f"Total checked: {total_checked}")
    print(f"Total mismatches: {mismatches}")
    
    if mismatches == 0:
        print("SUCCESS: Optimized solver is mathematically identical to naive solver.")
        return True
    else:
        print("FAILURE: Mismatches found.")
        return False

if __name__ == "__main__":
    success = run_equivalence_test()
    sys.exit(0 if success else 1)
