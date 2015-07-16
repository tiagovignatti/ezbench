#!/usr/bin/awk -f

BEGIN {
	min = 10000000
}

{
	val = $1

	if (val < min)
		min = val
	if (val > max)
		max = val
	sum += val
	sum2 += val * val 

	# percentiles
	array[NR] = val
}

END {
	avg = sum / NR
	var= ((sum*sum) - sum2)/(NR-1)

	asort(array)

	p50 = int(NR / 2)
	p90 = int(NR * 0.9)
	p95 = int(NR * 0.95)
	p99 = int(NR * 0.99)

	print avg " min/p50/90/95/99/max/std = " min " / " array[p50] " / " array[p90] " / " array[p95] " / " array[p99] " / " max " / " sqrt(var) " n=" NR
}
