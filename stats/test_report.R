#!/usr/bin/Rscript

args <- commandArgs(trailingOnly = TRUE)
if(length(args) != 2) {
    cat("Usage:\n\t./test_report.R input.csv output.png\n\n")
    q(save="no")
}

data <- read.csv(args[1])

d <- density(data[[1]])

png(args[2], width = 1900, height = 200)

layout(matrix(c(1,2), 1), c(3.5,1), c(1,3))
par(mar=c(4.3, 4.3, 2.0, 0.1))

plot(data[[1]], ylab="FPS", xlab="FPS sample", main="Time series of the FPS",
     cex.lab=1.5, cex.axis=1.5, cex.main=1.5, cex.sub=1.5)
lines(data[[1]], type="l")
abline(h=mean(data[[1]]),col=4)
abline(h=median(data[[1]]),col=2)

plot(d, xlab="FPS", main="Density function of the FPS", cex.lab=1.5,
     cex.axis=1.5, cex.main=1.5, cex.sub=1.5)
abline(v=mean(data[[1]]),col=4)
abline(v=median(data[[1]]),col=2)
